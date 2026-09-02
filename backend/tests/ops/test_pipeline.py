"""The daily orchestrator: three phases, one run row.

What these protect is the failure policy. A dead RSS feed must not cost the site
its brief, and an extraction that runs out of retries must not hide the articles
that were fetched anyway — so most of these break one phase on purpose and then
assert the others still ran.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.brief.models import DailyBrief
from apps.common.exceptions import AppError, ContentFilteredError
from apps.ingest.models import RawArticle
from apps.ops.models import ExtractionRun
from apps.ops.services import pipeline as pipeline_module
from apps.ops.services.pipeline import MAX_ARTICLES_PER_RUN, PENDING_TTL_DAYS, run_daily
from apps.wiki.models import Entity, Linkage

pytestmark = pytest.mark.django_db

BODY = "OpenAI 于本周正式发布 GPT-5，主打推理能力提升。业界普遍认为混合专家模型仍是主流路线。"

INGEST_TOTALS = {
    "sources": 2,
    "fetched": 12,
    "filtered": 4,
    "deduped": 3,
    "saved": 5,
    "failed": 0,
    "elapsed_ms": 4210,
    "per_source": [],
}


def make_article(index: int = 0, *, status: str = "pending") -> RawArticle:
    return RawArticle.objects.create(
        title=f"测试文章 {index}",
        url=f"https://example.com/news/{index}",
        content=BODY,
        content_hash=f"daily-hash-{index:04d}",
        publish_time=timezone.now(),
        extract_status=status,
    )


def entities_payload(article_id: int) -> dict:
    return {
        "entities": [
            {
                "name": "OpenAI",
                "type": "org",
                "aliases": [],
                "summary": "美国人工智能研究公司。",
                "confidence": 0.95,
                "evidence": "OpenAI 于本周正式发布 GPT-5",
                "raw_article_id": article_id,
            }
        ]
    }


def concepts_payload(article_id: int) -> dict:
    return {
        "concepts": [
            {
                "name": "混合专家模型",
                "namespace": "technique",
                "definition": "把模型拆成多个专家子网络的架构路线。",
                "signals": [],
                "confidence": 0.85,
                "evidence": "业界普遍认为混合专家模型仍是主流路线",
                "raw_article_id": article_id,
            }
        ]
    }


def linkages_payload(article_id: int) -> dict:
    return {
        "linkages": [
            {
                "subject": "OpenAI",
                "predicate": "采用",
                "object_type": "concept",
                "object": "混合专家模型",
                "confidence": 0.8,
                "evidence": "业界普遍认为混合专家模型仍是主流路线",
                "raw_article_id": article_id,
            }
        ]
    }


BRIEF_PAYLOAD = {
    "title": "今日 AI 简报",
    "content_md": "OpenAI 发布了 GPT-5[1]。",
    "used_indexes": [1],
}


def script_full_day(mock_llm, article_id: int) -> None:
    """Queue the four calls a clean day makes: three steps plus the brief."""
    mock_llm.push_json(entities_payload(article_id))
    mock_llm.push_json(concepts_payload(article_id))
    mock_llm.push_json(linkages_payload(article_id))
    mock_llm.push_json(BRIEF_PAYLOAD)


@pytest.fixture
def stub_ingest(monkeypatch):
    """Replace the network sweep. Real ingest has its own tests."""
    calls = []

    def _fetch(article_fetcher=None, source_ids=None):
        calls.append({"article_fetcher": article_fetcher, "source_ids": source_ids})
        return dict(INGEST_TOTALS)

    monkeypatch.setattr(pipeline_module, "fetch_all_enabled", _fetch)
    return calls


def daily(mock_llm, **kwargs):
    return run_daily(client=mock_llm, sleep=lambda _: None, **kwargs)


# --- the happy path -----------------------------------------------------


def test_all_three_phases_land_on_one_run(stub_ingest, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)

    run = daily(mock_llm)

    assert ExtractionRun.objects.count() == 1
    assert set(run.step_metrics) == {
        "ingest",
        "extract_entities",
        "extract_concepts",
        "extract_linkages",
        "persist",
        "brief",
    }
    assert run.status == "success"


def test_the_work_of_all_three_phases_is_visible(stub_ingest, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)

    daily(mock_llm)

    assert Entity.objects.count() == 1
    assert Linkage.objects.count() == 1
    assert DailyBrief.objects.count() == 1


def test_the_ingest_step_records_the_sweep_totals(stub_ingest, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)

    run = daily(mock_llm)

    assert run.step_metrics["ingest"] == {
        "status": "done",
        "elapsed_ms": 4210,
        "fetched": 12,
        "filtered": 4,
        "deduped": 3,
        "saved": 5,
    }


def test_tokens_and_cost_cover_the_brief_as_well_as_the_extraction(stub_ingest, mock_llm):
    article = make_article(1)
    mock_llm.push_json(entities_payload(article.pk), prompt_tokens=100, completion_tokens=10)
    mock_llm.push_json(concepts_payload(article.pk), prompt_tokens=200, completion_tokens=20)
    mock_llm.push_json(linkages_payload(article.pk), prompt_tokens=300, completion_tokens=30)
    mock_llm.push_json(BRIEF_PAYLOAD, prompt_tokens=400, completion_tokens=40)

    run = daily(mock_llm)

    assert run.prompt_tokens == 1000
    assert run.completion_tokens == 100
    assert run.total_tokens == 1100
    assert run.cost_cny > 0


def test_the_trigger_and_prompt_snapshot_are_recorded(stub_ingest, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)

    run = daily(mock_llm, trigger="manual")

    assert run.trigger == "manual"
    assert run.prompt_versions["brief.daily"] >= 1


def test_source_ids_are_passed_through_to_the_sweep(stub_ingest, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)

    daily(mock_llm, source_ids=[7, 9])

    assert stub_ingest[0]["source_ids"] == [7, 9]


def test_a_prepared_run_is_reused_rather_than_replaced(stub_ingest, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)
    prepared = ExtractionRun.objects.create(run_id="prepared-run-01", trigger="cron")

    run = daily(mock_llm, run=prepared)

    assert run.pk == prepared.pk
    assert ExtractionRun.objects.count() == 1


def test_the_run_is_closed_out(stub_ingest, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)

    run = daily(mock_llm)

    assert run.finished_at is not None
    assert run.elapsed_ms >= 0
    assert run.error_message == ""


# --- one phase fails ----------------------------------------------------


def test_a_failed_ingest_does_not_stop_the_rest(monkeypatch, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)

    def _boom(article_fetcher=None, source_ids=None):
        raise RuntimeError("feed host unreachable")

    monkeypatch.setattr(pipeline_module, "fetch_all_enabled", _boom)

    run = daily(mock_llm)

    assert run.status == "partial"
    assert run.step_metrics["ingest"]["status"] == "failed"
    assert "feed host unreachable" in run.step_metrics["ingest"]["error_message"]
    assert run.step_metrics["brief"]["status"] == "done"
    assert DailyBrief.objects.count() == 1


def test_a_failed_extraction_still_leaves_a_brief(stub_ingest, mock_llm):
    make_article(1)
    for _ in range(3):
        mock_llm.push("这不是 JSON")
    mock_llm.push_json(BRIEF_PAYLOAD)

    run = daily(mock_llm)

    assert run.status == "partial"
    assert run.step_metrics["extract_entities"]["status"] == "failed"
    assert run.step_metrics["brief"]["status"] == "done"
    assert "extract:" in run.error_message


def test_a_failed_brief_leaves_the_extraction_intact(stub_ingest, mock_llm):
    article = make_article(1)
    mock_llm.push_json(entities_payload(article.pk))
    mock_llm.push_json(concepts_payload(article.pk))
    mock_llm.push_json(linkages_payload(article.pk))
    for _ in range(3):
        mock_llm.push("也不是 JSON")

    run = daily(mock_llm)

    assert run.status == "partial"
    assert run.step_metrics["brief"]["status"] == "failed"
    assert Entity.objects.count() == 1
    assert not DailyBrief.objects.exists()


def test_a_failed_briefs_tokens_are_still_billed(stub_ingest, mock_llm):
    article = make_article(1)
    mock_llm.push_json(entities_payload(article.pk))
    mock_llm.push_json(concepts_payload(article.pk))
    mock_llm.push_json(linkages_payload(article.pk))
    for _ in range(3):
        mock_llm.push("也不是 JSON", prompt_tokens=500, completion_tokens=5)

    run = daily(mock_llm)

    assert run.step_metrics["brief"]["prompt_tokens"] == 1500
    assert run.step_metrics["brief"]["attempts"] == 3


def test_a_brief_refused_by_the_content_filter_is_skipped_not_failed(stub_ingest, mock_llm):
    """A refusal is not a fault, and no retry would change the answer.

    The extraction underneath is already saved and every claim on the site stays
    traceable; losing one day's prose should not colour the run partial. Seen for
    real on 2026-08-29 against arXiv material, which is not remotely sensitive.
    """
    article = make_article(1)
    mock_llm.push_json(entities_payload(article.pk))
    mock_llm.push_json(concepts_payload(article.pk))
    mock_llm.push_json(linkages_payload(article.pk))
    mock_llm.push_error(ContentFilteredError("LLM refused to answer on safety grounds"))

    run = daily(mock_llm)

    assert run.step_metrics["brief"]["status"] == "skipped"
    assert run.status == "success"
    assert "brief:" not in run.error_message
    assert Entity.objects.count() == 1


def test_a_refused_brief_is_only_attempted_once(stub_ingest, mock_llm):
    article = make_article(1)
    mock_llm.push_json(entities_payload(article.pk))
    mock_llm.push_json(concepts_payload(article.pk))
    mock_llm.push_json(linkages_payload(article.pk))
    mock_llm.push_error(ContentFilteredError("refused"))

    daily(mock_llm)

    assert mock_llm.call_count == 4


def test_everything_failing_leaves_the_run_failed(monkeypatch, mock_llm):
    make_article(1)
    for _ in range(6):
        mock_llm.push("这不是 JSON")

    def _boom(article_fetcher=None, source_ids=None):
        raise RuntimeError("feed host unreachable")

    monkeypatch.setattr(pipeline_module, "fetch_all_enabled", _boom)

    run = daily(mock_llm)

    assert run.status == "failed"


# --- nothing to do ------------------------------------------------------


def test_nothing_pending_skips_the_extraction_without_calling_the_model(stub_ingest, mock_llm):
    make_article(1, status="extracted")
    mock_llm.push_json(BRIEF_PAYLOAD)

    run = daily(mock_llm)

    assert "extract_entities" not in run.step_metrics
    assert mock_llm.call_count == 1
    assert run.status == "success"


def test_pending_articles_older_than_the_ttl_are_retired(stub_ingest, mock_llm):
    """ADR-019. Ingest brings in several times what one run can extract, so the
    oldest pending rows are unreachable by construction — the queue is drained
    newest-first. Left alone they accumulate forever and misreport the backlog.
    """
    stale = make_article(1)
    RawArticle.objects.filter(pk=stale.pk).update(
        publish_time=timezone.now() - timedelta(days=PENDING_TTL_DAYS + 1)
    )
    daily(mock_llm)

    stale.refresh_from_db()
    assert stale.extract_status == "skipped"
    # Retired rather than extracted, so the model was never reached at all —
    # the brief has no material either once the only article is retired.
    assert mock_llm.call_count == 0


def test_recent_pending_articles_are_left_alone(stub_ingest, mock_llm):
    fresh = make_article(2)
    RawArticle.objects.filter(pk=fresh.pk).update(
        publish_time=timezone.now() - timedelta(days=PENDING_TTL_DAYS - 1)
    )
    script_full_day(mock_llm, fresh.pk)

    daily(mock_llm)

    fresh.refresh_from_db()
    assert fresh.extract_status == "extracted"


def test_retiring_the_backlog_never_touches_an_article_that_already_ran(stub_ingest, mock_llm):
    """`skipped` means "we chose not to"; it must not overwrite a real outcome."""
    for status in ("extracted", "failed"):
        article = make_article(hash(status) % 1000, status=status)
        RawArticle.objects.filter(pk=article.pk).update(
            publish_time=timezone.now() - timedelta(days=PENDING_TTL_DAYS + 30)
        )
    mock_llm.push_json(BRIEF_PAYLOAD)

    daily(mock_llm)

    assert set(RawArticle.objects.values_list("extract_status", flat=True)) == {"extracted", "failed"}


def test_an_undated_pending_article_is_not_retired(stub_ingest, mock_llm):
    """Nothing is known about its age, so nothing can be concluded about it."""
    undated = make_article(3)
    RawArticle.objects.filter(pk=undated.pk).update(publish_time=None)
    script_full_day(mock_llm, undated.pk)

    daily(mock_llm)

    undated.refresh_from_db()
    assert undated.extract_status == "extracted"


def test_a_day_with_no_articles_skips_the_brief_without_failing(stub_ingest, mock_llm):
    run = daily(mock_llm)

    assert run.step_metrics["brief"]["status"] == "skipped"
    assert run.status == "success"
    assert mock_llm.call_count == 0


def test_a_backlog_is_capped_per_run(stub_ingest, mock_llm, settings):
    settings.EXTRACT_BATCH_SIZE = 100
    for index in range(MAX_ARTICLES_PER_RUN + 5):
        make_article(index)
    article_ids = list(RawArticle.objects.values_list("pk", flat=True))
    mock_llm.push_json(entities_payload(article_ids[0]))
    mock_llm.push_json(concepts_payload(article_ids[0]))
    mock_llm.push_json(linkages_payload(article_ids[0]))
    mock_llm.push_json(BRIEF_PAYLOAD)

    run = daily(mock_llm)

    assert run.articles_in == MAX_ARTICLES_PER_RUN
    assert RawArticle.objects.filter(extract_status="pending").count() == 5


def test_per_article_ingest_failures_reach_the_panel_without_failing_the_step(monkeypatch, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)

    def _partly_broken(article_fetcher=None, source_ids=None):
        return dict(INGEST_TOTALS) | {"failed": 3}

    monkeypatch.setattr(pipeline_module, "fetch_all_enabled", _partly_broken)

    run = daily(mock_llm)

    # Three unreadable pages out of twelve is a normal day for a web crawler.
    # The sweep already logged them; the step is still "done" and the run is
    # still a success, but the count belongs on the panel.
    assert run.status == "success"
    assert run.step_metrics["ingest"]["status"] == "done"
    assert run.step_metrics["ingest"]["failed"] == 3


def test_a_clean_sweep_carries_no_failure_count(stub_ingest, mock_llm):
    article = make_article(1)
    script_full_day(mock_llm, article.pk)

    run = daily(mock_llm)

    assert "failed" not in run.step_metrics["ingest"]


def test_a_brief_failing_for_a_reason_other_than_an_empty_day_fails_the_step(
    stub_ingest, mock_llm, monkeypatch
):
    article = make_article(1)
    mock_llm.push_json(entities_payload(article.pk))
    mock_llm.push_json(concepts_payload(article.pk))
    mock_llm.push_json(linkages_payload(article.pk))

    def _boom(*args, **kwargs):
        raise AppError("prompt brief.daily 没有可用版本", code="PROMPT_RENDER_ERROR")

    monkeypatch.setattr(pipeline_module, "generate_daily_brief", _boom)

    run = daily(mock_llm)

    # `NO_ARTICLES` is the one AppError that means "nothing to do". Every other
    # one is a real fault and must not be quietly filed as "skipped".
    assert run.status == "partial"
    assert run.step_metrics["brief"]["status"] == "failed"
    assert "没有可用版本" in run.step_metrics["brief"]["error_message"]
    assert "brief:" in run.error_message
    assert Entity.objects.count() == 1
