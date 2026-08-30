"""One pass through the whole thing: RssSource in, DailyBrief out.

The unit tests each guard one seam. This guards the seams *between* them — the
places where a contract change passes every module's own tests and still breaks
the product, because the pipeline is a chain of six steps that only ever run
together in production.

Real database, real ORM, real serializers, real prompt templates from the
migration. The two things faked are the ones that would otherwise leave the
process: the network (feed and article fetchers) and the model.
"""

import pytest
from django.utils import timezone

from apps.brief.models import DailyBrief
from apps.common.exceptions import FetchError
from apps.ingest.fetchers.base import FetchedArticle
from apps.ingest.fetchers.rss import FeedEntry
from apps.ingest.models import RawArticle, RssSource
from apps.ingest.services import ingest as ingest_service
from apps.ops.models import ExtractionRun
from apps.ops.services.pipeline import run_daily
from apps.wiki.models import Concept, Entity, Evidence, Linkage

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# --- the corpus the "network" will serve ---------------------------------

ARTICLES = {
    "https://example.com/news/gpt5": (
        "OpenAI 发布 GPT-5",
        "OpenAI 于本周正式发布 GPT-5，主打推理能力提升。该公司表示新模型将在下月向 API 客户开放。"
        "业界普遍认为混合专家模型仍是当前主流路线。",
    ),
    "https://example.com/news/claude": (
        "Anthropic 更新 Claude",
        "Anthropic 发布了新版 Claude，重点改进了长上下文处理。该模型同样采用混合专家模型架构。",
    ),
    "https://example.com/news/chips": (
        "英伟达公布新一代加速卡",
        "英伟达发布新一代 AI 加速卡，宣称训练吞吐较上代提升一倍。OpenAI 与 Anthropic 均为其客户。",
    ),
}


class StubFetcher:
    """An `ArticleFetcher` that serves `ARTICLES` instead of the web."""

    def fetch(self, url: str) -> FetchedArticle:
        title, body = ARTICLES[url]
        return FetchedArticle(url=url, title=title, content=body, lang="zh")


@pytest.fixture
def wired_network(monkeypatch):
    """A source whose feed lists every article in `ARTICLES`."""
    source = RssSource.objects.create(name="示例源", url="https://example.com/feed.xml", enabled=True)

    def fake_fetch_feed(url: str, timeout: float = 20.0) -> list[FeedEntry]:
        return [
            FeedEntry(title=title, url=article_url, summary="", author="", publish_time=timezone.now())
            for article_url, (title, _body) in ARTICLES.items()
        ]

    monkeypatch.setattr(ingest_service, "fetch_feed", fake_fetch_feed)
    return source


# --- what the model says -------------------------------------------------


def _entities(ids: list[int]) -> dict:
    return {
        "entities": [
            {
                "name": "OpenAI",
                "type": "org",
                "aliases": ["Open AI"],
                "summary": "美国人工智能研究公司。",
                "confidence": 0.95,
                "evidence": "OpenAI 于本周正式发布 GPT-5",
                "raw_article_id": ids[0],
            },
            {
                "name": "GPT-5",
                "type": "model",
                "aliases": [],
                "summary": "OpenAI 的新一代模型。",
                "confidence": 0.9,
                "evidence": "正式发布 GPT-5，主打推理能力提升",
                "raw_article_id": ids[0],
            },
            {
                "name": "Anthropic",
                "type": "org",
                "aliases": [],
                "summary": "美国人工智能公司。",
                "confidence": 0.93,
                "evidence": "Anthropic 发布了新版 Claude",
                "raw_article_id": ids[1],
            },
            {
                "name": "英伟达",
                "type": "org",
                "aliases": ["NVIDIA"],
                "summary": "GPU 与 AI 加速硬件厂商。",
                "confidence": 0.92,
                "evidence": "英伟达发布新一代 AI 加速卡",
                "raw_article_id": ids[2],
            },
        ]
    }


def _concepts(ids: list[int]) -> dict:
    return {
        "concepts": [
            {
                "name": "混合专家模型",
                "namespace": "technique",
                "definition": "把模型拆成多个专家子网络的架构路线。",
                "signals": ["混合专家", "MoE"],
                "confidence": 0.85,
                "evidence": "业界普遍认为混合专家模型仍是当前主流路线",
                "raw_article_id": ids[0],
            }
        ]
    }


def _linkages(ids: list[int]) -> dict:
    return {
        "linkages": [
            {
                "subject": "OpenAI",
                # Deliberately a synonym: `normalize_predicate` should fold it
                # into 发布 before it reaches the graph.
                "predicate": "推出",
                "object_type": "entity",
                "object": "GPT-5",
                "confidence": 0.92,
                "evidence": "OpenAI 于本周正式发布 GPT-5",
                "raw_article_id": ids[0],
            },
            {
                "subject": "GPT-5",
                "predicate": "基于",
                "object_type": "concept",
                "object": "混合专家模型",
                "confidence": 0.7,
                "evidence": "业界普遍认为混合专家模型仍是当前主流路线",
                "raw_article_id": ids[0],
            },
            {
                "subject": "Anthropic",
                "predicate": "合作",
                "object_type": "entity",
                "object": "英伟达",
                "confidence": 0.6,
                "evidence": "OpenAI 与 Anthropic 均为其客户",
                "raw_article_id": ids[2],
            },
        ]
    }


BRIEF = {
    "title": "今日 AI 简报",
    "content_md": "OpenAI 发布了 GPT-5[1]，Anthropic 更新了 Claude[2]。",
    "used_indexes": [1, 2],
    # The model volunteering citation metadata nobody asked for. None of it may
    # survive into the stored brief.
    "citations": [{"index": 1, "url": "https://hallucinated.example.com/x", "title": "假的"}],
}


def _script(mock_llm, ids: list[int]) -> None:
    mock_llm.push_json(_entities(ids))
    mock_llm.push_json(_concepts(ids))
    mock_llm.push_json(_linkages(ids))
    mock_llm.push_json(BRIEF)


@pytest.fixture
def completed_run(wired_network, mock_llm, monkeypatch):
    """A finished `run_daily`, with the model scripted against real article ids.

    Ingest has to run before the ids exist, so the script is queued from inside
    the ingest call rather than up front.
    """
    real_sweep = ingest_service.fetch_all_enabled

    def sweep_then_script(*args, **kwargs):
        totals = real_sweep(*args, **kwargs)
        ids = list(RawArticle.objects.order_by("pk").values_list("pk", flat=True))
        _script(mock_llm, ids)
        return totals

    monkeypatch.setattr("apps.ops.services.pipeline.fetch_all_enabled", sweep_then_script)

    return run_daily(
        trigger="cron",
        client=mock_llm,
        article_fetcher=StubFetcher(),
        sleep=lambda _: None,
    )


# --- the run itself ------------------------------------------------------


def test_a_clean_day_ends_in_success(completed_run):
    assert completed_run.status == "success"
    assert completed_run.error_message == ""
    assert completed_run.finished_at is not None


def test_every_model_has_rows_at_the_end(completed_run):
    """The assertion the whole file exists for: nothing in the chain was skipped."""
    assert RssSource.objects.count() == 1
    assert RawArticle.objects.count() == len(ARTICLES)
    assert Entity.objects.count() == 4
    assert Concept.objects.count() == 1
    assert Linkage.objects.count() == 3
    assert Evidence.objects.count() == 8
    assert DailyBrief.objects.count() == 1
    assert ExtractionRun.objects.count() == 1


def test_all_six_steps_are_recorded_on_one_run(completed_run):
    # The ops panel renders exactly these, in this order.
    assert list(completed_run.step_metrics) == [
        "ingest",
        "extract_entities",
        "extract_concepts",
        "extract_linkages",
        "persist",
        "brief",
    ]
    assert all(step["elapsed_ms"] >= 0 for step in completed_run.step_metrics.values())


def test_the_run_accounts_for_every_call(completed_run, mock_llm):
    # Three extraction steps plus the brief, and nothing retried.
    assert mock_llm.call_count == 4
    assert completed_run.total_tokens == 480
    assert completed_run.cost_cny > 0
    assert completed_run.trigger == "cron"


def test_the_articles_are_marked_extracted(completed_run):
    assert RawArticle.objects.filter(extract_status="extracted").count() == len(ARTICLES)
    assert not RawArticle.objects.filter(extract_status="pending").exists()


# --- the chain held together --------------------------------------------


def test_every_claim_traces_back_to_an_article_that_contains_it(completed_run):
    """The product promise, checked against the database rather than the prompt.

    Each snippet must actually occur in the body of the article it cites —
    whitespace-insensitively, the same comparison the validator makes.
    """
    assert Evidence.objects.exists()

    for evidence in Evidence.objects.select_related("raw_article"):
        haystack = "".join(evidence.raw_article.content.split())
        assert "".join(evidence.snippet.split()) in haystack
        assert evidence.extraction_run_id == completed_run.pk
        assert evidence.prompt_version == 1


def test_evidence_is_attached_to_exactly_one_kind_of_target(completed_run):
    for evidence in Evidence.objects.all():
        targets = [evidence.entity_id, evidence.concept_id, evidence.linkage_id]
        assert sum(target is not None for target in targets) == 1


def test_the_graph_has_edges_between_the_things_that_were_extracted(completed_run):
    published = Linkage.objects.get(subject_entity__name="OpenAI", object_entity__name="GPT-5")

    # A synonym in, the canonical predicate out.
    assert published.predicate == "发布"
    assert Linkage.objects.filter(object_concept__name="混合专家模型").exists()
    assert Linkage.objects.filter(object_entity__isnull=False).count() == 2


def test_the_brief_cites_the_articles_that_were_ingested(completed_run):
    brief = DailyBrief.objects.get()
    real_urls = set(RawArticle.objects.values_list("url", flat=True))

    assert brief.extraction_run_id == completed_run.pk
    assert len(brief.citations) == 2
    assert all(citation["url"] in real_urls for citation in brief.citations)
    assert all(
        RawArticle.objects.filter(pk=citation["raw_article_id"]).exists() for citation in brief.citations
    )
    # The URL the model volunteered is not one of the ingested articles and must
    # not have survived the round trip.
    assert not any("hallucinated" in citation["url"] for citation in brief.citations)


def test_the_run_is_served_by_the_api_that_the_frontend_polls(completed_run, client):
    response = client.get(f"/api/v1/ops/runs/{completed_run.run_id}/")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert set(response.json()["step_metrics"]) == set(completed_run.step_metrics)


def test_an_extracted_entity_is_reachable_with_its_evidence(completed_run, client):
    entity = Entity.objects.get(name="OpenAI")

    payload = client.get(f"/api/v1/wiki/entities/{entity.pk}/").json()

    assert payload["name"] == "OpenAI"
    assert payload["linkages"], "the entity page would have nothing to show"
    evidence = payload["linkages"][0]["evidences"][0]
    # Every field the evidence card renders, all the way from the model call.
    assert evidence["snippet"]
    assert evidence["prompt_key"] == "wiki.extract_linkages"
    assert evidence["prompt_version"] == 1
    assert evidence["run_id"] == completed_run.run_id
    assert evidence["article"]["url"] in ARTICLES


def test_the_graph_endpoint_can_draw_what_was_extracted(completed_run, client):
    payload = client.get("/api/v1/wiki/graph/?limit=50").json()

    assert len(payload["nodes"]) == 5  # four entities plus one concept
    assert len(payload["links"]) == 3
    assert payload["truncated"] is False


# --- the same chain, one link broken -------------------------------------


def test_a_second_run_over_the_same_feed_adds_nothing_and_stays_clean(wired_network, mock_llm, monkeypatch):
    """Re-running a day must be idempotent, or the demo data doubles every cron.

    Nothing new is ingested, so nothing is pending, so the extraction is skipped
    and only the brief is rewritten in place.
    """
    real_sweep = ingest_service.fetch_all_enabled
    scripted = []

    def sweep_then_script(*args, **kwargs):
        totals = real_sweep(*args, **kwargs)
        if not scripted:
            _script(mock_llm, list(RawArticle.objects.order_by("pk").values_list("pk", flat=True)))
            scripted.append(True)
        else:
            mock_llm.push_json(BRIEF)  # the brief is regenerated; extraction is not
        return totals

    monkeypatch.setattr("apps.ops.services.pipeline.fetch_all_enabled", sweep_then_script)

    kwargs = {"client": mock_llm, "article_fetcher": StubFetcher(), "sleep": lambda _: None}
    first = run_daily(trigger="cron", **kwargs)
    second = run_daily(trigger="cron", **kwargs)

    assert (first.status, second.status) == ("success", "success")
    assert RawArticle.objects.count() == len(ARTICLES)
    assert Entity.objects.count() == 4
    assert Linkage.objects.count() == 3
    assert DailyBrief.objects.count() == 1
    assert second.step_metrics["ingest"]["deduped"] == len(ARTICLES)
    assert "extract_entities" not in second.step_metrics


def test_a_dead_feed_still_produces_a_brief_from_yesterdays_articles(
    completed_run, wired_network, mock_llm, monkeypatch
):
    """The failure policy, end to end: one broken link does not empty the site."""

    def dead_feed(url: str, timeout: float = 20.0):
        raise FetchError("connection reset by peer")

    monkeypatch.setattr(ingest_service, "fetch_feed", dead_feed)
    mock_llm.push_json(BRIEF)

    run = run_daily(trigger="cron", client=mock_llm, article_fetcher=StubFetcher(), sleep=lambda _: None)

    # The sweep reports the dead source on the source row, not as a crash, so
    # the run is a success with nothing new — and the brief still gets written.
    assert run.status == "success"
    assert run.step_metrics["ingest"]["fetched"] == 0
    assert "connection reset" in RssSource.objects.get().last_error
    assert DailyBrief.objects.count() == 1
