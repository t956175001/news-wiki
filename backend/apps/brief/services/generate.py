"""Turn one day's articles and extraction output into a cited brief.

The rule that matters here: **the model never supplies a citation.** It is asked
which source indexes it used, and everything else — article id, title, URL,
publish time — is read back out of the database by index. A brief whose links
came from the model would be a brief whose links can be hallucinated, and the
whole project is a bet that citations are worth more than prose.

Contract: `docs/ARCHITECTURE.md` section 3.4 (`DailyBrief.citations`) and the
`brief.daily` section of `docs/PROMPTS.md`.
"""

import datetime as dt
import json
import logging
import time
from collections.abc import Sequence

from django.db.models import Q

from apps.common.exceptions import AppError, SchemaError
from apps.common.llm import LLMClient, get_llm_client
from apps.common.llm.invoke import StepMeta, invoke_json
from apps.ingest.models import RawArticle
from apps.ops.models import ExtractionRun
from apps.wiki.models import Entity, Linkage

from ..models import DailyBrief

logger = logging.getLogger(__name__)

PROMPT_BRIEF = "brief.daily"
STEP_BRIEF = "brief"

# A day of AI news is 10-30 articles. Twenty is enough material for a brief and
# short enough that the whole thing still fits one call.
MAX_ARTICLES = 20

# These are hints about what the pipeline found important, not the corpus — the
# articles themselves are already in the prompt. A few dozen is plenty.
MAX_ENTITIES = 20
MAX_LINKAGES = 30

TITLE_LIMIT = DailyBrief._meta.get_field("title").max_length


# --- material -----------------------------------------------------------


def _articles_for(date: dt.date) -> list[RawArticle]:
    """The day's articles, newest first.

    Dated by `publish_time` when the feed gave one and by `fetched_at` when it
    did not, so an article with no publish date still lands in the brief for the
    day it arrived instead of disappearing.
    """
    return list(
        RawArticle.objects.filter(
            Q(publish_time__date=date) | Q(publish_time__isnull=True, fetched_at__date=date)
        ).order_by("-publish_time", "-fetched_at")[:MAX_ARTICLES]
    )


def _material(
    run: ExtractionRun | None, articles: Sequence[RawArticle]
) -> tuple[list[Entity], list[Linkage]]:
    """The entities and relations to hand the model as context.

    Scoped to *run* when there is one, so the brief describes what today's run
    actually found. Without a run — regenerating an old brief, say — it falls
    back to whatever was ever extracted from these same articles.
    """
    if run is not None:
        entity_filter = Q(evidences__extraction_run=run)
        linkage_filter = Q(evidences__extraction_run=run)
    else:
        entity_filter = Q(evidences__raw_article__in=articles)
        linkage_filter = Q(evidences__raw_article__in=articles)

    entities = list(Entity.objects.filter(entity_filter).distinct()[:MAX_ENTITIES])
    linkages = list(
        Linkage.objects.filter(linkage_filter)
        .select_related("subject_entity", "object_entity", "object_concept")
        .distinct()
        .order_by("-confidence")[:MAX_LINKAGES]
    )
    return entities, linkages


def _articles_json(by_index: dict[int, RawArticle]) -> str:
    """The numbered source list. `index` is what the model cites as `[n]`."""
    return json.dumps(
        [
            {
                "index": index,
                "id": article.pk,
                "title": article.title,
                "url": article.url,
                "publish_time": _iso(article.publish_time),
            }
            for index, article in sorted(by_index.items())
        ],
        ensure_ascii=False,
    )


def _entities_json(entities: Sequence[Entity]) -> str:
    return json.dumps(
        [{"name": item.name, "type": item.entity_type, "summary": item.summary} for item in entities],
        ensure_ascii=False,
    )


def _linkages_json(linkages: Sequence[Linkage]) -> str:
    return json.dumps(
        [
            {
                "subject": item.subject_entity.name,
                "predicate": item.predicate,
                "object": (item.object_entity or item.object_concept).name,
            }
            for item in linkages
        ],
        ensure_ascii=False,
    )


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


# --- output -------------------------------------------------------------


def validate_brief(payload: dict) -> dict:
    """Check the `brief.daily` payload's shape. Raises `SchemaError` to retry.

    Only the shape: whether the citations make sense is not the model's call to
    make, and `_citations` settles it against the database afterwards.
    """
    if not isinstance(payload, dict):
        raise SchemaError(f"Expected a JSON object at the top level, got {type(payload).__name__}")

    for field in ("title", "content_md"):
        value = payload.get(field)
        if not isinstance(value, str):
            raise SchemaError(f"brief.{field} must be a string, got {type(value).__name__}")
        if not value.strip():
            raise SchemaError(f"brief.{field} must not be empty")

    if not isinstance(payload.get("used_indexes"), list):
        raise SchemaError(
            f"brief.used_indexes must be an array, got {type(payload.get('used_indexes')).__name__}"
        )

    return payload


def _as_index(raw) -> int | None:
    """Coerce one entry of `used_indexes` to an int, or None if it is not one."""
    # bool is an int in Python, and `[true]` is not a source number.
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().lstrip("+").isdigit():
        return int(raw)
    return None


def _citations(used_indexes: Sequence, by_index: dict[int, RawArticle], run_id: str) -> list[dict]:
    """Build the citation list from the database, using the model only for *which*.

    Anything the model cites that is not a source it was given is dropped with a
    warning: a dangling `[7]` in the text is a cosmetic bug, while a citation
    pointing at an article that was never in the material is a lie.
    """
    citations = []
    seen: set[int] = set()

    for raw in used_indexes:
        index = _as_index(raw)
        if index is None:
            logger.warning("run_id=%s brief cited %r, which is not a source number; ignored", run_id, raw)
            continue
        if index in seen:
            continue
        article = by_index.get(index)
        if article is None:
            logger.warning(
                "run_id=%s brief cited source [%s], outside the 1-%s it was given; ignored",
                run_id,
                index,
                len(by_index),
            )
            continue

        seen.add(index)
        citations.append(
            {
                "index": index,
                "raw_article_id": article.pk,
                "title": article.title,
                "url": article.url,
                "publish_time": _iso(article.publish_time),
            }
        )

    # Ordered by index so the reference list at the foot of the brief counts up,
    # whatever order the model happened to list them in.
    return sorted(citations, key=lambda citation: citation["index"])


# --- entry point --------------------------------------------------------


def generate_daily_brief(
    date: dt.date,
    run: ExtractionRun | None = None,
    *,
    client: LLMClient | None = None,
    trigger: str = "manual",
    sleep=time.sleep,
) -> tuple[DailyBrief, StepMeta]:
    """Write (or rewrite) the brief for *date* and return it with its metrics.

    Returns `(brief, StepMeta)` — the same shape as the extraction steps in
    `apps/wiki/services/extract_pipeline.py` — so `run_daily` can fold the
    brief's tokens into the same run accounting as everything else.

    Raises `AppError("NO_ARTICLES")` when the day is empty, without calling the
    model: there is nothing to summarise and nothing worth paying for.
    """
    articles = _articles_for(date)
    if not articles:
        raise AppError(f"{date} 没有可用于生成简报的文章。", code="NO_ARTICLES")

    by_index = {index: article for index, article in enumerate(articles, start=1)}
    entities, linkages = _material(run, articles)
    run_id = run.run_id if run is not None else "-"

    payload, meta = invoke_json(
        PROMPT_BRIEF,
        {
            "date": date.isoformat(),
            "articles_json": _articles_json(by_index),
            "entities_json": _entities_json(entities),
            "linkages_json": _linkages_json(linkages),
        },
        client=client or get_llm_client(),
        run_id=run_id,
        validate=validate_brief,
        trigger=trigger,
        sleep=sleep,
    )

    citations = _citations(payload["used_indexes"], by_index, run_id)
    if not citations:
        # Not an error — the row is still worth keeping — but a brief with no
        # sources is the failure mode this whole design exists to prevent.
        logger.warning("run_id=%s brief for %s cites nothing", run_id, date)

    brief, _created = DailyBrief.objects.update_or_create(
        date=date,
        defaults={
            "title": payload["title"].strip()[:TITLE_LIMIT],
            "content_md": payload["content_md"],
            "citations": citations,
            "model_name": meta.model,
            "extraction_run": run,
        },
    )

    meta.count = len(citations)
    logger.info(
        "run_id=%s brief for %s written: %s citation(s) from %s article(s)",
        run_id,
        date,
        len(citations),
        len(articles),
    )
    return brief, meta
