"""The three-step extraction pipeline: entities -> concepts -> linkages.

Serial by design (ADR-002). Each step gets the previous step's output as a
*closed candidate set*, which is the whole trick: asking a model for relations
without an entity list gets you "OpenAI", "Open AI" and "OpenAI 公司" as three
separate nodes. Giving it a list and demanding verbatim names moves that problem
out of post-processing and into the prompt.

All three steps run. A pipeline that quietly stops after entities produces a
graph with no edges, which is a graph with nothing to say.

Failure policy (ARCHITECTURE section 2): a failed step does not roll back the
steps before it. `persist` is one transaction; the run as a whole is not.
"""

import json
import logging
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import BudgetExceededError, ExtractionStepError
from apps.common.llm import LLMClient, get_llm_client
from apps.common.llm.invoke import StepMeta, invoke_json, ms_since
from apps.common.llm.pricing import estimate_cost
from apps.common.prompts.service import get_version
from apps.ingest.models import RawArticle
from apps.ops.models import ExtractionRun
from apps.wiki.models import Concept, Entity, Evidence, Linkage

from .normalize import merge_aliases, normalize_name, normalize_predicate
from .validators import validate_concepts, validate_entities, validate_linkages

logger = logging.getLogger(__name__)

STEP_ENTITIES = "extract_entities"
STEP_CONCEPTS = "extract_concepts"
STEP_LINKAGES = "extract_linkages"
STEP_PERSIST = "persist"

PROMPT_ENTITIES = "wiki.extract_entities"
PROMPT_CONCEPTS = "wiki.extract_concepts"
PROMPT_LINKAGES = "wiki.extract_linkages"
PROMPT_BRIEF = "brief.daily"

# Snapshotted at the start of every run and frozen for its duration
# (ARCHITECTURE section 8.4), so "extracted by v1" stays true after v2 lands.
SNAPSHOT_PROMPT_KEYS = (PROMPT_ENTITIES, PROMPT_CONCEPTS, PROMPT_LINKAGES, PROMPT_BRIEF)

_STEP_BY_PROMPT = {
    PROMPT_ENTITIES: STEP_ENTITIES,
    PROMPT_CONCEPTS: STEP_CONCEPTS,
    PROMPT_LINKAGES: STEP_LINKAGES,
}

# ARCHITECTURE 3.2 documents Evidence.snippet as "原文片段，≤500 字". The prompts
# ask for 200; this is the backstop for when the model ignores that.
SNIPPET_LIMIT = 500


@dataclass
class ExtractionOutcome:
    """What `execute_extraction` concluded, for the caller to finalise the run."""

    status: str
    error: str = ""


# --- corpus -------------------------------------------------------------


def _body(article: RawArticle) -> str:
    """The article text as the model will see it, truncated per settings.

    Evidence is verified against this, not against the full row: the model can
    only quote what it was shown.
    """
    return (article.content or "")[: settings.EXTRACT_CONTENT_LIMIT]


def build_corpus(articles: Sequence[RawArticle]) -> str:
    """Render articles into the corpus format documented in PROMPTS.md.

    `ARTICLE_ID` is the load-bearing part: it is the only thing tying an
    extracted claim back to a source, so it is emitted first for every article.
    """
    blocks = []
    for article in articles:
        publish_time = ""
        if article.publish_time is not None:
            publish_time = timezone.localtime(article.publish_time).isoformat()
        blocks.append(
            "\n".join(
                [
                    f"ARTICLE_ID: {article.pk}",
                    f"TITLE: {article.title}",
                    f"URL: {article.url}",
                    f"PUBLISH_TIME: {publish_time}",
                    "CONTENT:",
                    _body(article),
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def corpus_texts(articles: Sequence[RawArticle]) -> dict[int, str]:
    """`{article_id: text}` for the same bodies `build_corpus` emitted."""
    return {article.pk: _body(article) for article in articles}


# --- prompt material ----------------------------------------------------


def _entities_json(entities: Iterable[dict]) -> str:
    """The entity list handed to steps 2 and 3 — names and types only.

    Summaries and evidence would triple the token cost of a list whose only job
    is to be a closed set of names the model must choose from.
    """
    return json.dumps(
        [{"name": item["name"], "type": item["type"]} for item in entities],
        ensure_ascii=False,
    )


def _concepts_json(concepts: Iterable[dict]) -> str:
    return json.dumps(
        [{"name": item["name"], "namespace": item["namespace"]} for item in concepts],
        ensure_ascii=False,
    )


# --- the three steps ----------------------------------------------------


def extract_entities(
    corpus: str,
    allowed_ids: Iterable[int],
    *,
    client: LLMClient | None = None,
    run_id: str = "-",
    article_texts: dict[int, str] | None = None,
    trigger: str = "manual",
    sleep=time.sleep,
) -> tuple[list[dict], StepMeta]:
    """Step 1: concrete entities out of the corpus."""
    allowed = set(allowed_ids)

    def _validate(payload):
        return validate_entities(payload, allowed, article_texts=article_texts)

    (items, skipped), meta = invoke_json(
        PROMPT_ENTITIES,
        {"raw_text": corpus},
        client=client or get_llm_client(),
        run_id=run_id,
        validate=_validate,
        trigger=trigger,
        sleep=sleep,
    )
    meta.count = len(items)
    meta.skipped = skipped
    return items, meta


def extract_concepts(
    corpus: str,
    entities: Sequence[dict],
    allowed_ids: Iterable[int],
    *,
    client: LLMClient | None = None,
    run_id: str = "-",
    article_texts: dict[int, str] | None = None,
    trigger: str = "manual",
    sleep=time.sleep,
) -> tuple[list[dict], StepMeta]:
    """Step 2: abstract concepts, told which entities are already spoken for."""
    allowed = set(allowed_ids)

    def _validate(payload):
        return validate_concepts(payload, allowed, article_texts=article_texts)

    (items, skipped), meta = invoke_json(
        PROMPT_CONCEPTS,
        {"raw_text": corpus, "entities_json": _entities_json(entities)},
        client=client or get_llm_client(),
        run_id=run_id,
        validate=_validate,
        trigger=trigger,
        sleep=sleep,
    )
    meta.count = len(items)
    meta.skipped = skipped
    return items, meta


def extract_linkages(
    corpus: str,
    entities: Sequence[dict],
    concepts: Sequence[dict],
    allowed_ids: Iterable[int],
    *,
    client: LLMClient | None = None,
    run_id: str = "-",
    article_texts: dict[int, str] | None = None,
    trigger: str = "manual",
    sleep=time.sleep,
) -> tuple[list[dict], StepMeta]:
    """Step 3: relations, restricted to the names steps 1 and 2 produced."""
    allowed = set(allowed_ids)
    entity_names = [item["name"] for item in entities]
    concept_names = [item["name"] for item in concepts]

    def _validate(payload):
        return validate_linkages(payload, allowed, entity_names, concept_names, article_texts=article_texts)

    (items, skipped), meta = invoke_json(
        PROMPT_LINKAGES,
        {
            "raw_text": corpus,
            "entities_json": _entities_json(entities),
            "concepts_json": _concepts_json(concepts),
        },
        client=client or get_llm_client(),
        run_id=run_id,
        validate=_validate,
        trigger=trigger,
        sleep=sleep,
    )
    meta.count = len(items)
    meta.skipped = skipped
    return items, meta


# --- persistence --------------------------------------------------------


def _seen_at(article: RawArticle | None, fallback):
    """When an entity was "seen": the article's publish time, not the run's.

    A run in August that ingests a July article should say the entity was first
    seen in July, otherwise every entity looks like it appeared the day the
    crawler happened to reach it.
    """
    if article is not None and article.publish_time is not None:
        return article.publish_time
    return fallback


def _save_entities(items, articles_by_id, now) -> dict[tuple[str, str], Entity]:
    """Upsert entities, returned keyed by their uniqueness pair.

    Keyed on `(normalized_name, entity_type)` — the same pair as
    `uniq_entity_norm_type` — because "Claude" the model and "Claude" the product
    are two rows, and attaching one's evidence to the other would be silent
    corruption of the thing this whole project is selling.
    """
    saved: dict[tuple[str, str], Entity] = {}

    for item in items:
        normalized = normalize_name(item["name"])
        seen_at = _seen_at(articles_by_id.get(item["raw_article_id"]), now)

        entity, created = Entity.objects.get_or_create(
            normalized_name=normalized,
            entity_type=item["type"],
            defaults={
                "name": item["name"],
                "aliases": merge_aliases([], item["aliases"]),
                "summary": item["summary"],
                "confidence": item["confidence"],
                "mention_count": 0,
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
            },
        )

        aliases = list(item["aliases"])
        if not created and item["name"] != entity.name:
            # A different surface form of a name we already have is itself an
            # alias worth keeping; the stored `name` stays put so links and
            # headings do not churn between runs.
            aliases.append(item["name"])
        entity.aliases = merge_aliases(entity.aliases, aliases)

        entity.mention_count += 1
        if item["summary"]:
            # Latest wins: for a news wiki the newest description of an entity is
            # usually the most useful one.
            entity.summary = item["summary"]
        # Confidence is "are we sure this is a real entity", which only grows
        # with corroboration.
        entity.confidence = max(entity.confidence, item["confidence"])
        entity.first_seen_at = min(filter(None, [entity.first_seen_at, seen_at]), default=seen_at)
        entity.last_seen_at = max(filter(None, [entity.last_seen_at, seen_at]), default=seen_at)
        entity.save()

        saved[(normalized, item["type"])] = entity

    return saved


def _save_concepts(items) -> dict[tuple[str, str], Concept]:
    """Upsert concepts, keyed on `(namespace, name)` to match uniq_concept_ns_name."""
    saved: dict[tuple[str, str], Concept] = {}

    for item in items:
        concept, _ = Concept.objects.get_or_create(
            namespace=item["namespace"],
            name=item["name"],
            defaults={
                "definition": item["definition"],
                "signals": merge_aliases([], item["signals"]),
                "confidence": item["confidence"],
            },
        )
        # Signals accumulate the same way aliases do: each corpus contributes a
        # few more of the words that point at this concept.
        concept.signals = merge_aliases(concept.signals, item["signals"])
        if item["definition"]:
            concept.definition = item["definition"]
        concept.confidence = max(concept.confidence, item["confidence"])
        concept.save()

        saved[(item["namespace"], item["name"])] = concept

    return saved


def _by_name(saved: dict) -> dict[str, object]:
    """Collapse a uniqueness-keyed map to a name lookup for linkage resolution.

    Linkages only carry names, so a name that maps to two rows (same word, two
    types or namespaces) has to pick one. First wins, which makes the choice
    stable across re-runs rather than dependent on dict ordering.
    """
    lookup: dict[str, object] = {}
    for saved_object in saved.values():
        lookup.setdefault(normalize_name(saved_object.name), saved_object)
    return lookup


def _save_linkages(items, entities_by_name, concepts_by_name) -> tuple[list[tuple[Linkage, dict]], int]:
    """Create linkages, returning `(linkage, source_item)` pairs and a skip count."""
    created: list[tuple[Linkage, dict]] = []
    unresolved = 0

    for item in items:
        subject = entities_by_name.get(normalize_name(item["subject"]))
        if subject is None:
            unresolved += 1
            continue

        object_key = normalize_name(item["object"])
        if item["object_type"] == "entity":
            object_entity = entities_by_name.get(object_key)
            object_concept = None
            resolved = object_entity
        else:
            object_entity = None
            object_concept = concepts_by_name.get(object_key)
            resolved = object_concept

        if resolved is None:
            # The validator already dropped names outside the candidate sets, so
            # reaching here means the referenced item failed to persist.
            unresolved += 1
            continue

        linkage, was_created = Linkage.objects.get_or_create(
            subject_entity=subject,
            predicate=normalize_predicate(item["predicate"]),
            object_entity=object_entity,
            object_concept=object_concept,
            defaults={"confidence": item["confidence"]},
        )
        if not was_created and item["confidence"] > linkage.confidence:
            linkage.confidence = item["confidence"]
            linkage.save(update_fields=["confidence", "updated_at"])

        created.append((linkage, item))

    return created, unresolved


def _save_evidence(run, prompt_key, targets, articles_by_id, kind: str) -> int:
    """One Evidence row per extracted item that came with a usable quote.

    `prompt_version` is read from the run's snapshot rather than from the DB, so
    a prompt edited mid-run cannot relabel evidence produced before the edit.
    """
    version = run.prompt_versions.get(prompt_key, 0)
    rows = []

    for target, item in targets:
        snippet = item["evidence"]
        article = articles_by_id.get(item["raw_article_id"])
        if not snippet or article is None:
            continue
        rows.append(
            Evidence(
                raw_article=article,
                snippet=snippet[:SNIPPET_LIMIT],
                extraction_run=run,
                prompt_key=prompt_key,
                prompt_version=version,
                **{kind: target},
            )
        )

    Evidence.objects.bulk_create(rows)
    return len(rows)


@transaction.atomic
def persist(
    run: ExtractionRun,
    articles: Sequence[RawArticle],
    entities: Sequence[dict],
    concepts: Sequence[dict],
    linkages: Sequence[dict],
) -> dict:
    """Write one run's extraction results. All of it or none of it.

    Atomic because a half-written batch is worse than no batch: linkages whose
    endpoints are missing would show up as edges to nowhere on the graph.
    """
    now = timezone.now()
    articles_by_id = {article.pk: article for article in articles}

    saved_entities = _save_entities(entities, articles_by_id, now)
    saved_concepts = _save_concepts(concepts)
    saved_linkages, unresolved = _save_linkages(linkages, _by_name(saved_entities), _by_name(saved_concepts))

    entity_targets = [
        (saved_entities[(normalize_name(item["name"]), item["type"])], item) for item in entities
    ]
    concept_targets = [(saved_concepts[(item["namespace"], item["name"])], item) for item in concepts]

    evidence_count = (
        _save_evidence(run, PROMPT_ENTITIES, entity_targets, articles_by_id, "entity")
        + _save_evidence(run, PROMPT_CONCEPTS, concept_targets, articles_by_id, "concept")
        + _save_evidence(run, PROMPT_LINKAGES, saved_linkages, articles_by_id, "linkage")
    )

    counts = {
        "entities": len(saved_entities),
        "concepts": len(saved_concepts),
        "linkages": len(saved_linkages),
        "evidences": evidence_count,
    }
    if unresolved:
        counts["skipped_unresolved_refs"] = unresolved
    return counts


# --- orchestration ------------------------------------------------------


def _batches(articles: Sequence[RawArticle], size: int) -> Iterable[Sequence[RawArticle]]:
    for start in range(0, len(articles), size):
        yield articles[start : start + size]


def record_step(run: ExtractionRun, totals: dict[str, StepMeta], step: str, meta: StepMeta) -> None:
    """Fold a step's metrics into the run and save immediately.

    Saved after every step, not at the end: extraction is a long task that the
    frontend follows by polling `/api/v1/ops/runs/{run_id}/`, and metrics written
    only on completion would leave the progress panel blank for the whole run.
    """
    running = totals.setdefault(step, StepMeta())
    running.merge(meta)
    run.step_metrics[step] = running.as_dict()
    run.save(update_fields=["step_metrics"])


def finish_run(
    run: ExtractionRun,
    totals: dict[str, StepMeta],
    status: str,
    started: float,
    error: str = "",
) -> ExtractionRun:
    """Close a run: final status, token totals, cost, and elapsed time.

    Cost is summed per step rather than over the run's grand totals because each
    step records the model that actually answered it, and a run can span models.
    """
    run.status = status
    run.error_message = error
    run.prompt_tokens = sum(meta.prompt_tokens for meta in totals.values())
    run.completion_tokens = sum(meta.completion_tokens for meta in totals.values())
    run.total_tokens = run.prompt_tokens + run.completion_tokens
    run.cost_cny = sum(
        (estimate_cost(meta.model, meta.prompt_tokens, meta.completion_tokens) for meta in totals.values()),
        Decimal("0"),
    )
    run.elapsed_ms = ms_since(started)
    run.finished_at = timezone.now()
    run.save()
    return run


def _mark_articles(articles: Sequence[RawArticle], extracted_ids: set[int]) -> None:
    """Stamp each article with whether its batch made it through all three steps."""
    all_ids = {article.pk for article in articles}
    failed_ids = all_ids - extracted_ids

    if extracted_ids:
        RawArticle.objects.filter(pk__in=extracted_ids).update(extract_status="extracted")
    if failed_ids:
        RawArticle.objects.filter(pk__in=failed_ids).update(extract_status="failed")


def start_run(trigger: str = "manual", articles_in: int = 0) -> ExtractionRun:
    """Open a run row with this moment's prompt versions frozen onto it.

    Separate from `run_extraction` because the HTTP layer needs the `run_id`
    before the work starts: the request returns it immediately and the frontend
    polls `/api/v1/ops/runs/{run_id}/` while a background thread does the work.
    """
    return ExtractionRun.objects.create(
        run_id=uuid.uuid4().hex,
        status="running",
        trigger=trigger,
        articles_in=articles_in,
        prompt_versions={key: get_version(key) for key in SNAPSHOT_PROMPT_KEYS},
    )


def execute_extraction(
    run: ExtractionRun,
    articles: Sequence[RawArticle],
    totals: dict[str, StepMeta],
    *,
    client: LLMClient | None = None,
    trigger: str = "manual",
    sleep=time.sleep,
) -> ExtractionOutcome:
    """Run the three steps plus persist onto an existing *run*.

    Writes its metrics into *totals* rather than finalising the run, so that
    `run_daily` can fold the brief's numbers into the same accounting before the
    single `finish_run` that closes the row.
    """
    articles = list(articles)
    run.articles_in = len(articles)
    run.save(update_fields=["articles_in"])
    logger.info("run_id=%s extraction started over %s article(s)", run.run_id, len(articles))

    llm = client or get_llm_client()
    all_entities: list[dict] = []
    all_concepts: list[dict] = []
    all_linkages: list[dict] = []
    extracted_ids: set[int] = set()
    completed_steps = 0
    error = ""

    try:
        for batch in _batches(articles, settings.EXTRACT_BATCH_SIZE):
            corpus = build_corpus(batch)
            allowed = {article.pk for article in batch}
            texts = corpus_texts(batch)
            step_kwargs = {
                "client": llm,
                "run_id": run.run_id,
                "article_texts": texts,
                "trigger": trigger,
                "sleep": sleep,
            }

            # Accumulated step by step rather than at the end of the batch: if
            # step 2 dies, step 1's entities have already been banked and will
            # still be persisted. That is what "partial" is supposed to mean.
            entities, meta = extract_entities(corpus, allowed, **step_kwargs)
            record_step(run, totals, STEP_ENTITIES, meta)
            all_entities.extend(entities)
            completed_steps += 1

            concepts, meta = extract_concepts(corpus, entities, allowed, **step_kwargs)
            record_step(run, totals, STEP_CONCEPTS, meta)
            all_concepts.extend(concepts)
            completed_steps += 1

            linkages, meta = extract_linkages(corpus, entities, concepts, allowed, **step_kwargs)
            record_step(run, totals, STEP_LINKAGES, meta)
            all_linkages.extend(linkages)
            completed_steps += 1

            # Only a batch that cleared all three steps counts as extracted. One
            # that banked entities but never got its relations is incomplete, and
            # labelling it "extracted" would hide it from any later retry.
            extracted_ids |= allowed

    except ExtractionStepError as exc:
        error = exc.detail
        run.step_metrics[_STEP_BY_PROMPT[exc.step]] = _merged_failure(totals, exc)
        run.save(update_fields=["step_metrics"])

    except BudgetExceededError as exc:
        # The guard fires before the request, so nothing was spent on this step.
        # The batches already done stay persisted; the run reports why it stopped.
        error = exc.detail
        logger.warning("run_id=%s stopped by the daily budget guard: %s", run.run_id, exc.detail)

    if all_entities or all_concepts or all_linkages:
        persist_started = time.monotonic()
        counts = persist(run, articles, all_entities, all_concepts, all_linkages)
        run.step_metrics[STEP_PERSIST] = {
            "status": "done",
            "elapsed_ms": ms_since(persist_started),
            **counts,
        }
        run.entities_saved = counts["entities"]
        run.concepts_saved = counts["concepts"]
        run.linkages_saved = counts["linkages"]

    if not error:
        status = "success"
    elif completed_steps or run.entities_saved:
        status = "partial"
    else:
        status = "failed"

    _mark_articles(articles, extracted_ids if status != "failed" else set())
    return ExtractionOutcome(status=status, error=error)


def run_extraction(
    articles: Sequence[RawArticle],
    trigger: str = "manual",
    *,
    run: ExtractionRun | None = None,
    client: LLMClient | None = None,
    sleep=time.sleep,
) -> ExtractionRun:
    """Run all three steps over *articles* and record everything on an ExtractionRun.

    Batched at `settings.EXTRACT_BATCH_SIZE` articles per call. Each batch runs
    its own three steps, because step 2 and 3 must be given the entity list from
    the same corpus they are quoting.

    A batch that fails part-way stops the run, but everything extracted before it
    is still persisted: `status` becomes `partial` rather than `failed` whenever
    at least one step completed.
    """
    started = time.monotonic()
    run = run or start_run(trigger)
    totals: dict[str, StepMeta] = {}

    outcome = execute_extraction(run, articles, totals, client=client, trigger=trigger, sleep=sleep)
    finish_run(run, totals, outcome.status, started, outcome.error)

    logger.info(
        "run_id=%s extraction %s: %s entities, %s concepts, %s linkages, %s tokens, %s CNY",
        run.run_id,
        run.status,
        run.entities_saved,
        run.concepts_saved,
        run.linkages_saved,
        run.total_tokens,
        run.cost_cny,
    )
    return run


def _merged_failure(totals: dict[str, StepMeta], exc: ExtractionStepError) -> dict:
    """Fold a failed step's metrics into whatever earlier batches recorded for it."""
    step = _STEP_BY_PROMPT[exc.step]
    running = totals.setdefault(step, StepMeta())
    running.merge(StepMeta.from_metrics(exc.metrics))
    return running.as_dict()
