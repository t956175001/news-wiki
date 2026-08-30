"""Management command tests.

`seed_demo` is the command a visitor's whole experience rests on: if the fixture
path breaks, the public site is an empty wiki. The default mode is therefore
tested against a real fixture file and a real `loaddata`, not a mock.

`--live` is exercised with a scripted model and a stub fetcher — it is the only
code path in the project that would otherwise spend money to test.
"""

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.brief.models import DailyBrief
from apps.brief.services.generate import generate_daily_brief
from apps.ingest.fetchers.base import FetchedArticle
from apps.ingest.fetchers.rss import FeedEntry
from apps.ingest.models import RawArticle, RssSource
from apps.ingest.services import ingest as ingest_service
from apps.ops.models import ExtractionRun
from apps.wiki.models import Concept, Entity, Evidence, Linkage
from apps.wiki.services.extract_pipeline import run_extraction

pytestmark = pytest.mark.django_db

REPO_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "demo.json"


def run(*args, **options) -> str:
    out = StringIO()
    call_command(*args, stdout=out, stderr=out, **options)
    return out.getvalue()


# --- seed_sources -------------------------------------------------------


def test_seed_sources_creates_the_documented_feeds():
    output = run("seed_sources")

    assert RssSource.objects.count() >= 4
    assert RssSource.objects.filter(enabled=True).count() >= 4
    assert "arXiv cs.AI" in output


def test_seed_sources_is_idempotent():
    run("seed_sources")
    run("seed_sources")

    assert RssSource.objects.count() == RssSource.objects.values("url").distinct().count()


def test_seed_sources_does_not_re_enable_a_source_an_operator_switched_off():
    run("seed_sources")
    source = RssSource.objects.first()
    source.enabled = False
    source.save(update_fields=["enabled"])

    run("seed_sources")

    source.refresh_from_db()
    assert source.enabled is False


def test_seed_sources_repairs_a_renamed_source():
    run("seed_sources")
    source = RssSource.objects.get(url="https://hnrss.org/frontpage")
    source.name = "手滑改错的名字"
    source.save(update_fields=["name"])

    output = run("seed_sources")

    source.refresh_from_db()
    assert source.name == "Hacker News Front Page"
    assert "~ Hacker News Front Page" in output


# --- seed_demo, default mode --------------------------------------------


def test_the_committed_fixture_exists():
    """The public demo is this file. Losing it empties the site."""
    assert REPO_FIXTURE.exists(), f"{REPO_FIXTURE} is missing"


def test_seed_demo_loads_the_committed_fixture():
    run("seed_demo")

    # PRD section 3's numbers, checked against what actually ships.
    assert Entity.objects.count() >= 60
    assert Linkage.objects.count() >= 80
    assert DailyBrief.objects.count() >= 7
    assert RawArticle.objects.count() >= 80
    assert Evidence.objects.exists()


def test_seed_demo_makes_no_model_calls(mock_llm):
    run("seed_demo")

    # The whole point of shipping a fixture: a visitor costs nothing.
    assert mock_llm.call_count == 0


def test_seed_demo_is_the_default_mode():
    def counts(output: str) -> list[str]:
        # Everything but the "Loaded ... in 0.7s" line, whose timing varies.
        return [line for line in output.splitlines() if not line.startswith("Loaded")]

    assert counts(run("seed_demo")) == counts(run("seed_demo", "--from-fixture"))


def test_running_seed_demo_twice_does_not_duplicate_anything():
    run("seed_demo")
    counts = (Entity.objects.count(), Linkage.objects.count(), DailyBrief.objects.count())

    run("seed_demo")

    assert (Entity.objects.count(), Linkage.objects.count(), DailyBrief.objects.count()) == counts


def test_seed_demo_reports_the_counts_it_loaded():
    output = run("seed_demo")

    for label in ("articles", "entities", "concepts", "linkages", "evidences", "briefs"):
        assert label in output


def test_a_missing_fixture_is_a_clear_error(tmp_path):
    with pytest.raises(CommandError, match="not found"):
        run("seed_demo", "--fixture", str(tmp_path / "nope.json"))


def test_the_fixture_and_live_modes_are_mutually_exclusive():
    with pytest.raises(CommandError):
        run("seed_demo", "--live", "--from-fixture")


# --- seed_demo --live ---------------------------------------------------

LIVE_BODY = "OpenAI 于本周正式发布 GPT-5，主打推理能力提升。业界普遍认为混合专家模型仍是主流路线。"


class StubFetcher:
    def fetch(self, url: str) -> FetchedArticle:
        return FetchedArticle(url=url, title="演示文章", content=LIVE_BODY, lang="zh")


@pytest.fixture
def live_network(monkeypatch):
    """One source, two articles, no sockets."""
    RssSource.objects.create(name="示例源", url="https://example.com/feed.xml", enabled=True)

    def fake_feed(url: str, timeout: float = 20.0) -> list[FeedEntry]:
        return [
            FeedEntry(
                title=f"演示文章 {n}",
                url=f"https://example.com/demo/{n}",
                summary="",
                author="",
                publish_time=timezone.now(),
            )
            for n in range(2)
        ]

    monkeypatch.setattr(ingest_service, "fetch_feed", fake_feed)
    monkeypatch.setattr(
        "apps.common.management.commands.seed_demo.fetch_all_enabled",
        lambda: ingest_service.fetch_all_enabled(article_fetcher=StubFetcher()),
    )


@pytest.fixture
def scripted_live(mock_llm, monkeypatch):
    """Answer each model call as it is made, not all of them up front.

    The extraction prompts have to cite real article ids, and those do not exist
    until ingest has run. Queuing lazily also keeps the order right when there is
    more than one run: a brief queued eagerly at the end of run 1 would be handed
    to run 2's entity step instead.
    """

    def script_then_extract(articles, *args, **kwargs):
        article_id = articles[0].pk
        mock_llm.push_json(
            {
                "entities": [
                    {
                        "name": "OpenAI",
                        "type": "org",
                        "aliases": [],
                        "summary": "美国人工智能研究公司。",
                        "confidence": 0.95,
                        "evidence": "OpenAI 于本周正式发布 GPT-5",
                        "raw_article_id": article_id,
                    },
                    {
                        "name": "GPT-5",
                        "type": "model",
                        "aliases": [],
                        "summary": "新一代模型。",
                        "confidence": 0.9,
                        "evidence": "正式发布 GPT-5",
                        "raw_article_id": article_id,
                    },
                ]
            }
        )
        mock_llm.push_json(
            {
                "concepts": [
                    {
                        "name": "混合专家模型",
                        "namespace": "technique",
                        "definition": "多专家子网络架构。",
                        "signals": [],
                        "confidence": 0.85,
                        "evidence": "业界普遍认为混合专家模型仍是主流路线",
                        "raw_article_id": article_id,
                    }
                ]
            }
        )
        mock_llm.push_json(
            {
                "linkages": [
                    {
                        "subject": "OpenAI",
                        "predicate": "发布",
                        "object_type": "entity",
                        "object": "GPT-5",
                        "confidence": 0.92,
                        "evidence": "OpenAI 于本周正式发布 GPT-5",
                        "raw_article_id": article_id,
                    }
                ]
            }
        )
        return run_extraction(articles, *args, **kwargs)

    def script_then_brief(*args, **kwargs):
        mock_llm.push_json(
            {
                "title": "今日 AI 简报",
                "content_md": "OpenAI 发布了 GPT-5[1]。",
                "used_indexes": [1],
            }
        )
        return generate_daily_brief(*args, **kwargs)

    monkeypatch.setattr("apps.common.management.commands.seed_demo.run_extraction", script_then_extract)
    monkeypatch.setattr("apps.common.management.commands.seed_demo.generate_daily_brief", script_then_brief)
    return mock_llm


def test_live_mode_builds_a_dataset_and_writes_the_fixture(live_network, scripted_live, tmp_path):
    target = tmp_path / "demo.json"

    output = run("seed_demo", "--live", "--fixture", str(target), "--budget-cny", "50")

    assert Entity.objects.count() == 2
    assert Concept.objects.count() == 1
    assert Linkage.objects.count() == 1
    assert DailyBrief.objects.count() == 1
    assert ExtractionRun.objects.get().trigger == "seed"
    assert "costs real money" in output
    assert target.exists()


def test_the_written_fixture_reloads_into_an_empty_database(live_network, scripted_live, tmp_path):
    target = tmp_path / "demo.json"
    run("seed_demo", "--live", "--fixture", str(target), "--budget-cny", "50")
    expected = (Entity.objects.count(), Linkage.objects.count(), Evidence.objects.count())

    for model in (Evidence, Linkage, Concept, Entity, DailyBrief, ExtractionRun, RawArticle):
        model.objects.all().delete()

    run("seed_demo", "--fixture", str(target))

    # A fixture that cannot be reloaded is a fixture that will fail on the
    # server, where there is nothing to fall back to.
    assert (Entity.objects.count(), Linkage.objects.count(), Evidence.objects.count()) == expected


def test_the_written_fixture_carries_no_prompt_templates(live_network, scripted_live, tmp_path):
    target = tmp_path / "demo.json"
    run("seed_demo", "--live", "--fixture", str(target), "--budget-cny", "50")

    models = {record["model"] for record in json.loads(target.read_text(encoding="utf-8"))}

    # The prompt rows come from a data migration. Two sources of truth for the
    # same four rows is how a fixture starts overwriting a newer prompt.
    assert not any(model.startswith("prompts.") for model in models)
    assert models <= {
        "ingest.rsssource",
        "ingest.rawarticle",
        "ops.extractionrun",
        "wiki.entity",
        "wiki.concept",
        "wiki.linkage",
        "wiki.evidence",
        "brief.dailybrief",
    }


def test_live_mode_drops_articles_it_never_extracted(live_network, scripted_live, tmp_path):
    """A sweep brings back more than `--articles` asks for; the surplus must not ship."""
    target = tmp_path / "demo.json"

    # The feed serves two articles but only one is asked for, so the other is
    # left pending — exactly what a real sweep does at `--articles 100`.
    output = run("seed_demo", "--live", "--articles", "1", "--fixture", str(target), "--budget-cny", "50")

    assert RawArticle.objects.count() == 1
    assert "Pruned 1 article" in output
    shipped = [
        record
        for record in json.loads(target.read_text(encoding="utf-8"))
        if record["model"] == "ingest.rawarticle"
    ]
    assert len(shipped) == 1


def test_briefs_never_cite_an_article_that_gets_pruned(live_network, scripted_live, tmp_path):
    """Pruning has to happen before the briefs are written, not after.

    `generate_daily_brief` takes its material from every article dated that day,
    including ones the extraction never reached. Pruning afterwards would leave
    the brief citing a `raw_article_id` that is no longer in the fixture.
    """
    RawArticle.objects.create(
        title="没被抽取的文章",
        url="https://example.com/demo/surplus",
        content="正文。",
        content_hash="surplus-hash",
        publish_time=timezone.now(),
        extract_status="pending",
    )
    target = tmp_path / "demo.json"

    run("seed_demo", "--live", "--keep-existing", "--fixture", str(target), "--budget-cny", "50")

    surviving = set(RawArticle.objects.values_list("pk", flat=True))
    for brief in DailyBrief.objects.all():
        cited = {citation["raw_article_id"] for citation in brief.citations}
        assert cited <= surviving, f"brief {brief.date} cites pruned article(s) {cited - surviving}"


def test_every_article_in_the_written_fixture_was_extracted(live_network, scripted_live, tmp_path):
    target = tmp_path / "demo.json"

    run("seed_demo", "--live", "--fixture", str(target), "--budget-cny", "50")

    records = json.loads(target.read_text(encoding="utf-8"))
    statuses = {
        record["fields"]["extract_status"] for record in records if record["model"] == "ingest.rawarticle"
    }
    assert statuses == {"extracted"}


def test_spread_days_redistributes_the_articles_across_an_archive(live_network, scripted_live, tmp_path):
    run(
        "seed_demo",
        "--live",
        "--spread-days",
        "2",
        "--fixture",
        str(tmp_path / "demo.json"),
        "--budget-cny",
        "50",
    )

    days = {timezone.localtime(a.publish_time).date() for a in RawArticle.objects.all()}

    # Two articles, two days: one brief each, which is what gives the archive
    # page something to page through.
    assert len(days) == 2
    assert DailyBrief.objects.count() == 2


def test_without_spread_days_the_feed_dates_are_left_alone(live_network, scripted_live, tmp_path):
    before = timezone.now()

    run("seed_demo", "--live", "--fixture", str(tmp_path / "demo.json"), "--budget-cny", "50")

    # The feed stamped these "now"; nothing should have moved them.
    assert all(a.publish_time >= before for a in RawArticle.objects.all())


def test_live_mode_clears_previous_data_first(live_network, scripted_live, tmp_path):
    stale = Entity.objects.create(name="过时实体", normalized_name="过时实体", entity_type="org", summary="")

    run("seed_demo", "--live", "--fixture", str(tmp_path / "demo.json"), "--budget-cny", "50")

    assert not Entity.objects.filter(pk=stale.pk).exists()


def test_keep_existing_leaves_earlier_rows_alone(live_network, scripted_live, tmp_path):
    kept = Entity.objects.create(name="保留实体", normalized_name="保留实体", entity_type="org", summary="")

    run(
        "seed_demo",
        "--live",
        "--keep-existing",
        "--fixture",
        str(tmp_path / "demo.json"),
        "--budget-cny",
        "50",
    )

    assert Entity.objects.filter(pk=kept.pk).exists()


def test_live_mode_refuses_when_there_is_nothing_to_extract(monkeypatch, mock_llm, tmp_path):
    RssSource.objects.create(name="空源", url="https://example.com/empty.xml", enabled=True)
    monkeypatch.setattr(ingest_service, "fetch_feed", lambda url, timeout=20.0: [])

    with pytest.raises(CommandError, match="Nothing pending"):
        run("seed_demo", "--live", "--fixture", str(tmp_path / "demo.json"))
