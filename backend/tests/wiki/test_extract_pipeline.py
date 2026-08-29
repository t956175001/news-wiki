"""Pipeline tests. Every LLM response is scripted; nothing leaves the process.

The behaviour these exist to protect: all three steps run and all three persist.
A pipeline that stops after entities produces a graph with no edges, which is the
exact failure this project was rebuilt to avoid — so several of these assert on
`Linkage` and `Evidence` counts rather than on return values.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.common.llm.pricing import estimate_cost
from apps.ingest.models import RawArticle
from apps.ops.models import ExtractionRun
from apps.wiki.models import Concept, Entity, Evidence, Linkage
from apps.wiki.services.extract_pipeline import (
    PROMPT_LINKAGES,
    SNAPSHOT_PROMPT_KEYS,
    build_corpus,
    run_extraction,
)

pytestmark = pytest.mark.django_db

BODY = "OpenAI 于本周正式发布 GPT-5，主打推理能力提升。业界普遍认为混合专家模型仍是主流路线。"

ENTITIES_PAYLOAD = {
    "entities": [
        {
            "name": "OpenAI",
            "type": "org",
            "aliases": ["Open AI"],
            "summary": "美国人工智能研究公司。",
            "confidence": 0.95,
            "evidence": "OpenAI 于本周正式发布 GPT-5",
            "raw_article_id": None,  # filled in per test
        },
        {
            "name": "GPT-5",
            "type": "model",
            "aliases": [],
            "summary": "OpenAI 的新一代模型。",
            "confidence": 0.9,
            "evidence": "正式发布 GPT-5，主打推理能力提升",
            "raw_article_id": None,
        },
    ]
}

CONCEPTS_PAYLOAD = {
    "concepts": [
        {
            "name": "混合专家模型",
            "namespace": "technique",
            "definition": "把模型拆成多个专家子网络的架构路线。",
            "signals": ["混合专家"],
            "confidence": 0.85,
            "evidence": "业界普遍认为混合专家模型仍是主流路线",
            "raw_article_id": None,
        }
    ]
}

LINKAGES_PAYLOAD = {
    "linkages": [
        {
            "subject": "OpenAI",
            "predicate": "发布",
            "object_type": "entity",
            "object": "GPT-5",
            "confidence": 0.92,
            "evidence": "OpenAI 于本周正式发布 GPT-5",
            "raw_article_id": None,
        },
        {
            "subject": "GPT-5",
            "predicate": "基于",
            "object_type": "concept",
            "object": "混合专家模型",
            "confidence": 0.7,
            "evidence": "业界普遍认为混合专家模型仍是主流路线",
            "raw_article_id": None,
        },
    ]
}


def _with_article(payload: dict, article_id: int) -> dict:
    """Stamp every item in a payload with the article it is supposed to cite."""
    root_key, items = next(iter(payload.items()))
    return {root_key: [{**item, "raw_article_id": article_id} for item in items]}


_UNSET = object()


def make_article(index: int = 0, *, content: str = BODY, publish_time=_UNSET) -> RawArticle:
    return RawArticle.objects.create(
        title=f"测试文章 {index}",
        url=f"https://example.com/news/{index}",
        content=content,
        content_hash=f"hash-{index:04d}",
        publish_time=timezone.now() if publish_time is _UNSET else publish_time,
    )


@pytest.fixture
def article():
    return make_article(0)


def script_success(mock_llm, article_id: int, *, linkages: dict | None = None):
    """Queue one full three-step conversation about *article_id*."""
    mock_llm.push_json(_with_article(ENTITIES_PAYLOAD, article_id))
    mock_llm.push_json(_with_article(CONCEPTS_PAYLOAD, article_id))
    mock_llm.push_json(_with_article(linkages or LINKAGES_PAYLOAD, article_id))


def run(articles, mock_llm, **kwargs):
    return run_extraction(articles, client=mock_llm, sleep=lambda _: None, **kwargs)


# --- corpus -------------------------------------------------------------


def test_build_corpus_matches_the_documented_format(article):
    corpus = build_corpus([article])

    assert corpus.startswith(f"ARTICLE_ID: {article.pk}\n")
    assert f"TITLE: {article.title}" in corpus
    assert f"URL: {article.url}" in corpus
    assert "PUBLISH_TIME: " in corpus
    assert corpus.endswith(f"CONTENT:\n{BODY}")


def test_build_corpus_separates_articles(article):
    second = make_article(1)

    corpus = build_corpus([article, second])

    assert "\n\n---\n\n" in corpus
    assert f"ARTICLE_ID: {second.pk}" in corpus


def test_build_corpus_truncates_bodies(settings):
    settings.EXTRACT_CONTENT_LIMIT = 6
    long_article = make_article(2, content="0123456789abcdef")

    assert build_corpus([long_article]).endswith("CONTENT:\n012345")


def test_build_corpus_tolerates_a_missing_publish_time():
    undated = make_article(3, publish_time=None)

    assert "PUBLISH_TIME: \n" in build_corpus([undated])


# --- happy path ---------------------------------------------------------


def test_all_three_steps_run_and_persist(article, mock_llm):
    script_success(mock_llm, article.pk)

    result = run([article], mock_llm)

    assert result.status == "success"
    assert mock_llm.call_count == 3
    assert Entity.objects.count() == 2
    assert Concept.objects.count() == 1
    # The whole point of the rebuild: the graph has edges.
    assert Linkage.objects.count() == 2
    assert Evidence.objects.count() == 5

    assert (result.entities_saved, result.concepts_saved, result.linkages_saved) == (2, 1, 2)
    assert result.articles_in == 1
    assert result.trigger == "manual"
    assert result.finished_at is not None
    assert result.elapsed_ms >= 0


def test_entity_fields_are_written_from_the_extraction(article, mock_llm):
    script_success(mock_llm, article.pk)

    run([article], mock_llm)

    entity = Entity.objects.get(normalized_name="openai")
    assert entity.name == "OpenAI"
    assert entity.entity_type == "org"
    assert entity.aliases == ["Open AI"]
    assert entity.summary == "美国人工智能研究公司。"
    assert entity.confidence == 0.95
    assert entity.mention_count == 1


def test_seen_timestamps_come_from_the_article_not_the_run(mock_llm):
    published = timezone.now() - dt.timedelta(days=30)
    old_article = make_article(4, publish_time=published)
    script_success(mock_llm, old_article.pk)

    run([old_article], mock_llm)

    entity = Entity.objects.get(normalized_name="openai")
    # A run in August that ingests a July article should not claim the entity
    # first appeared in August.
    assert entity.first_seen_at == published
    assert entity.last_seen_at == published


def test_concepts_are_persisted_with_their_namespace(article, mock_llm):
    script_success(mock_llm, article.pk)

    run([article], mock_llm)

    concept = Concept.objects.get(name="混合专家模型")
    assert concept.namespace == "technique"
    assert concept.signals == ["混合专家"]
    assert concept.definition.startswith("把模型拆成")


def test_linkages_point_at_the_persisted_objects(article, mock_llm):
    script_success(mock_llm, article.pk)

    run([article], mock_llm)

    to_entity = Linkage.objects.get(object_entity__isnull=False)
    assert to_entity.subject_entity.name == "OpenAI"
    assert to_entity.predicate == "发布"
    assert to_entity.object_entity.name == "GPT-5"
    assert to_entity.object_concept is None

    to_concept = Linkage.objects.get(object_concept__isnull=False)
    assert to_concept.subject_entity.name == "GPT-5"
    assert to_concept.object_concept.name == "混合专家模型"
    assert to_concept.object_entity is None


def test_evidence_records_the_prompt_key_and_version(article, mock_llm):
    script_success(mock_llm, article.pk)

    result = run([article], mock_llm)

    evidence = Evidence.objects.filter(linkage__isnull=False).first()
    assert evidence.prompt_key == PROMPT_LINKAGES
    assert evidence.prompt_version == 1
    assert evidence.extraction_run_id == result.pk
    assert evidence.raw_article_id == article.pk
    assert evidence.snippet == "OpenAI 于本周正式发布 GPT-5"

    # Each layer's evidence is labelled with the prompt that produced it.
    assert set(Evidence.objects.values_list("prompt_key", flat=True)) == set(SNAPSHOT_PROMPT_KEYS[:3])


def test_prompt_versions_are_snapshotted_at_the_start(article, mock_llm):
    script_success(mock_llm, article.pk)

    result = run([article], mock_llm)

    assert result.prompt_versions == dict.fromkeys(SNAPSHOT_PROMPT_KEYS, 1)


def test_processed_articles_are_marked_extracted(article, mock_llm):
    script_success(mock_llm, article.pk)

    run([article], mock_llm)
    article.refresh_from_db()

    assert article.extract_status == "extracted"


# --- normalisation in the pipeline --------------------------------------


def test_predicates_are_normalised_on_the_way_in(article, mock_llm):
    variant = {"linkages": [{**LINKAGES_PAYLOAD["linkages"][0], "predicate": "推出"}]}
    script_success(mock_llm, article.pk, linkages=variant)

    run([article], mock_llm)

    assert Linkage.objects.get().predicate == "发布"


def test_a_second_surface_form_of_a_name_becomes_an_alias(article, mock_llm):
    script_success(mock_llm, article.pk)
    run([article], mock_llm)

    second = make_article(5)
    renamed = {
        "entities": [{**ENTITIES_PAYLOAD["entities"][0], "name": "OPENAI", "aliases": []}],
    }
    mock_llm.push_json(_with_article(renamed, second.pk))
    mock_llm.push_json({"concepts": []})
    mock_llm.push_json({"linkages": []})
    run([second], mock_llm)

    entity = Entity.objects.get(normalized_name="openai")
    # The stored name stays put so links and headings do not churn.
    assert entity.name == "OpenAI"
    assert "OPENAI" in entity.aliases


# --- idempotence --------------------------------------------------------


def test_rerunning_the_same_batch_does_not_duplicate_rows(article, mock_llm):
    script_success(mock_llm, article.pk)
    run([article], mock_llm)

    script_success(mock_llm, article.pk)
    run([article], mock_llm)

    assert Entity.objects.count() == 2
    assert Concept.objects.count() == 1
    assert Linkage.objects.count() == 2
    assert Entity.objects.get(normalized_name="openai").mention_count == 2
    # Evidence is provenance, not deduplicated state: each run records what it
    # saw, with its own run_id and prompt version.
    assert Evidence.objects.count() == 10


def test_a_repeat_linkage_keeps_the_higher_confidence(article, mock_llm):
    script_success(mock_llm, article.pk)
    run([article], mock_llm)

    weaker = {"linkages": [{**LINKAGES_PAYLOAD["linkages"][0], "confidence": 0.1}]}
    script_success(mock_llm, article.pk, linkages=weaker)
    run([article], mock_llm)

    assert Linkage.objects.get(object_entity__isnull=False).confidence == 0.92


# --- failures -----------------------------------------------------------


def test_invalid_json_from_step_one_fails_the_run_after_three_attempts(article, mock_llm):
    for _ in range(3):
        mock_llm.push("这不是 JSON")

    result = run([article], mock_llm)

    assert result.status == "failed"
    assert result.step_metrics["extract_entities"]["attempts"] == 3
    assert result.step_metrics["extract_entities"]["status"] == "failed"
    assert "did not return JSON" in result.step_metrics["extract_entities"]["error_message"]
    assert mock_llm.call_count == 3
    assert Entity.objects.count() == 0


def test_a_missing_field_also_retries_and_then_fails(article, mock_llm):
    # Validation runs inside the retry loop, so a payload that parses but breaks
    # the schema gets the same three chances as unparseable output.
    for _ in range(3):
        mock_llm.push_json({"entities": [{"type": "org", "raw_article_id": article.pk}]})

    result = run([article], mock_llm)

    assert result.status == "failed"
    assert result.step_metrics["extract_entities"]["attempts"] == 3


def test_a_retry_that_succeeds_is_counted_but_does_not_fail_the_run(article, mock_llm):
    mock_llm.push("这不是 JSON")
    script_success(mock_llm, article.pk)

    result = run([article], mock_llm)

    assert result.status == "success"
    assert result.step_metrics["extract_entities"]["attempts"] == 2
    assert Entity.objects.count() == 2


def test_a_failure_in_step_two_leaves_step_one_persisted(article, mock_llm):
    mock_llm.push_json(_with_article(ENTITIES_PAYLOAD, article.pk))
    for _ in range(3):
        mock_llm.push("这不是 JSON")

    result = run([article], mock_llm)

    assert result.status == "partial"
    assert result.step_metrics["extract_entities"]["status"] == "done"
    assert result.step_metrics["extract_concepts"]["status"] == "failed"
    assert "extract_linkages" not in result.step_metrics
    # Nothing is rolled back: the entities the first step found are still there.
    assert Entity.objects.count() == 2
    assert result.entities_saved == 2
    assert Concept.objects.count() == 0
    assert Linkage.objects.count() == 0
    assert result.error_message


def test_articles_are_marked_failed_when_the_run_fails(article, mock_llm):
    for _ in range(3):
        mock_llm.push("这不是 JSON")

    run([article], mock_llm)
    article.refresh_from_db()

    assert article.extract_status == "failed"


def test_a_later_batch_failing_does_not_taint_the_earlier_one(settings, mock_llm):
    settings.EXTRACT_BATCH_SIZE = 2
    articles = [make_article(i) for i in range(10, 13)]

    script_success(mock_llm, articles[0].pk)  # batch 1 (articles 0 and 1)
    for _ in range(3):
        mock_llm.push("这不是 JSON")  # batch 2 dies on step 1

    result = run(articles, mock_llm)

    assert result.status == "partial"
    statuses = {a.pk: RawArticle.objects.get(pk=a.pk).extract_status for a in articles}
    assert statuses[articles[0].pk] == "extracted"
    assert statuses[articles[1].pk] == "extracted"
    assert statuses[articles[2].pk] == "failed"


# --- skipping -----------------------------------------------------------


def test_an_entity_citing_an_article_outside_the_batch_is_skipped(article, mock_llm):
    stray = {"entities": [{**ENTITIES_PAYLOAD["entities"][0], "raw_article_id": 999_999}]}
    mock_llm.push_json(stray)
    mock_llm.push_json({"concepts": []})
    mock_llm.push_json({"linkages": []})

    result = run([article], mock_llm)

    assert result.status == "success"
    assert Entity.objects.count() == 0
    assert result.step_metrics["extract_entities"]["skipped"] == {"skipped_invalid_article_ids": 1}


def test_a_linkage_referencing_an_unextracted_entity_is_skipped(article, mock_llm):
    unknown_ref = {
        "linkages": [{**LINKAGES_PAYLOAD["linkages"][0], "object": "Gemini 3"}],
    }
    script_success(mock_llm, article.pk, linkages=unknown_ref)

    result = run([article], mock_llm)

    assert Linkage.objects.count() == 0
    assert result.step_metrics["extract_linkages"]["skipped"] == {"skipped_unknown_refs": 1}


def test_empty_results_finish_cleanly_without_retrying(article, mock_llm):
    mock_llm.push_json({"entities": []})
    mock_llm.push_json({"concepts": []})
    mock_llm.push_json({"linkages": []})

    result = run([article], mock_llm)

    assert result.status == "success"
    # Three calls, not nine: an empty array is a valid answer, not a failure.
    assert mock_llm.call_count == 3
    assert (result.entities_saved, result.concepts_saved, result.linkages_saved) == (0, 0, 0)
    assert "persist" not in result.step_metrics


def test_no_articles_is_a_clean_no_op(mock_llm):
    result = run([], mock_llm)

    assert result.status == "success"
    assert mock_llm.call_count == 0
    assert result.articles_in == 0
    assert result.total_tokens == 0


# --- accounting and batching --------------------------------------------


def test_tokens_and_cost_are_aggregated_across_steps(article, mock_llm):
    script_success(mock_llm, article.pk)

    result = run([article], mock_llm)

    # FakeLLMClient bills 100 prompt + 20 completion per call, three calls.
    assert result.prompt_tokens == 300
    assert result.completion_tokens == 60
    assert result.total_tokens == 360
    assert result.cost_cny == 3 * estimate_cost("glm-4.7", 100, 20)
    assert result.cost_cny > Decimal("0")


def test_retried_attempts_are_billed_too(article, mock_llm):
    mock_llm.push("这不是 JSON")
    script_success(mock_llm, article.pk)

    result = run([article], mock_llm)

    # Four calls, not three: a retry is a request the invoice will list.
    assert result.prompt_tokens == 400
    assert result.step_metrics["extract_entities"]["prompt_tokens"] == 200


def test_batching_splits_the_corpus_across_calls(settings, mock_llm):
    settings.EXTRACT_BATCH_SIZE = 5
    articles = [make_article(i) for i in range(20, 32)]
    for _ in range(3):  # 12 articles -> batches of 5, 5, 2
        mock_llm.push_json({"entities": []})
        mock_llm.push_json({"concepts": []})
        mock_llm.push_json({"linkages": []})

    result = run(articles, mock_llm)

    assert result.status == "success"
    assert mock_llm.call_count == 9
    assert result.articles_in == 12
    # Each call sees only its own batch.
    assert mock_llm.prompt_at(0).count("ARTICLE_ID:") == 5
    assert mock_llm.prompt_at(6).count("ARTICLE_ID:") == 2


def test_batch_metrics_are_summed_not_overwritten(settings, mock_llm):
    settings.EXTRACT_BATCH_SIZE = 1
    articles = [make_article(i) for i in range(40, 42)]
    for item in articles:
        script_success(mock_llm, item.pk)

    result = run(articles, mock_llm)

    assert result.step_metrics["extract_entities"]["count"] == 4  # 2 entities x 2 batches
    assert result.step_metrics["extract_entities"]["attempts"] == 2
    assert result.step_metrics["extract_entities"]["prompt_tokens"] == 200


def test_step_metrics_become_visible_as_each_step_finishes(article, mock_llm):
    # Extraction is a long task the frontend follows by polling the run, so the
    # metrics have to land before the run is over.
    script_success(mock_llm, article.pk)
    seen: list[list[str]] = []
    inner_chat = mock_llm.chat

    def spy(messages, **opts):
        run_row = ExtractionRun.objects.filter(run_id=opts["run_id"]).first()
        seen.append(sorted(run_row.step_metrics) if run_row else [])
        return inner_chat(messages, **opts)

    mock_llm.chat = spy
    run([article], mock_llm)

    assert seen == [
        [],
        ["extract_entities"],
        ["extract_concepts", "extract_entities"],
    ]


def test_the_persist_step_is_reported_too(article, mock_llm):
    script_success(mock_llm, article.pk)

    result = run([article], mock_llm)

    persisted = result.step_metrics["persist"]
    assert persisted["status"] == "done"
    assert (persisted["entities"], persisted["concepts"], persisted["linkages"]) == (2, 1, 2)
    assert persisted["evidences"] == 5
    assert "elapsed_ms" in persisted


def test_the_run_is_visible_while_it_is_still_running(article, mock_llm):
    script_success(mock_llm, article.pk)

    result = run([article], mock_llm)

    # run_id is a bare uuid4 hex so it is safe in a URL.
    assert len(result.run_id) == 32
    assert ExtractionRun.objects.get(run_id=result.run_id).pk == result.pk


def test_the_trigger_is_recorded(article, mock_llm):
    script_success(mock_llm, article.pk)

    assert run([article], mock_llm, trigger="cron").trigger == "cron"


def test_evidence_from_an_unquotable_claim_is_not_created(article, mock_llm):
    quiet = {
        "entities": [{**ENTITIES_PAYLOAD["entities"][0], "evidence": ""}],
    }
    mock_llm.push_json(_with_article(quiet, article.pk))
    mock_llm.push_json({"concepts": []})
    mock_llm.push_json({"linkages": []})

    result = run([article], mock_llm)

    # PROMPTS.md: an entity with no quote is kept, its Evidence row is not.
    assert Entity.objects.count() == 1
    assert Evidence.objects.count() == 0
    assert result.step_metrics["extract_entities"]["skipped"] == {"evidence_empty": 1}


def test_an_unsourceable_quote_lands_with_reduced_confidence(article, mock_llm):
    invented = {
        "entities": [{**ENTITIES_PAYLOAD["entities"][0], "evidence": "原文里没有这句话"}],
    }
    mock_llm.push_json(_with_article(invented, article.pk))
    mock_llm.push_json({"concepts": []})
    mock_llm.push_json({"linkages": []})

    result = run([article], mock_llm)

    assert Entity.objects.get().confidence == pytest.approx(0.95 * 0.8)
    assert result.step_metrics["extract_entities"]["skipped"] == {"evidence_not_in_source": 1}


def test_the_entity_list_is_handed_to_the_later_steps(article, mock_llm):
    script_success(mock_llm, article.pk)

    run([article], mock_llm)

    # ADR-002: steps 2 and 3 get a closed candidate set, which is what keeps the
    # model from inventing a third spelling of a name it already used.
    concepts_prompt = mock_llm.prompt_at(1)
    linkages_prompt = mock_llm.prompt_at(2)
    assert '"name": "OpenAI"' in concepts_prompt
    assert '"name": "GPT-5"' in linkages_prompt
    assert '"name": "混合专家模型"' in linkages_prompt


def test_prompts_are_sent_as_json_object_requests(article, mock_llm):
    script_success(mock_llm, article.pk)

    run([article], mock_llm)

    assert all(call["opts"]["response_format"] == {"type": "json_object"} for call in mock_llm.calls)
    assert all(call["opts"]["run_id"] for call in mock_llm.calls)


def test_a_fenced_json_reply_is_still_accepted(article, mock_llm):
    import json

    payload = json.dumps(_with_article(ENTITIES_PAYLOAD, article.pk), ensure_ascii=False)
    mock_llm.push(f"```json\n{payload}\n```")
    mock_llm.push_json({"concepts": []})
    mock_llm.push_json({"linkages": []})

    result = run([article], mock_llm)

    # Unwrapping three characters is cheaper than spending a retry on them.
    assert result.status == "success"
    assert result.step_metrics["extract_entities"]["attempts"] == 1
    assert Entity.objects.count() == 2
