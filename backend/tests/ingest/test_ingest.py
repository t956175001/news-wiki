"""Ingest service tests: hashing, dedup, and failure isolation.

No test in this module touches the network — `fetch_feed` is monkeypatched and
the article fetcher is a stub.
"""

import datetime as dt
from unittest import mock

import pytest
from django.db import IntegrityError

from apps.common.exceptions import FetchError
from apps.ingest.fetchers.base import FetchedArticle
from apps.ingest.fetchers.rss import FeedEntry
from apps.ingest.models import RawArticle, RssSource
from apps.ingest.services import ingest as ingest_service
from apps.ingest.services.ingest import compute_hash, fetch_all_enabled, fetch_source

PUBLISHED = dt.datetime(2026, 8, 27, 10, 0, tzinfo=dt.UTC)


class StubFetcher:
    """An `ArticleFetcher` that never leaves the process."""

    def __init__(self, failures: dict[str, Exception] | None = None, content: str = "正文内容。"):
        self.failures = failures or {}
        self.content = content
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchedArticle:
        self.calls.append(url)
        if url in self.failures:
            raise self.failures[url]
        return FetchedArticle(url=url, title="page title", content=self.content, lang="zh")


def make_entry(n: int, title: str | None = None) -> FeedEntry:
    return FeedEntry(
        title=title if title is not None else f"文章 {n}",
        url=f"https://example.com/a{n}",
        summary=f"摘要 {n}",
        author="记者",
        publish_time=PUBLISHED,
    )


@pytest.fixture
def source(db) -> RssSource:
    return RssSource.objects.create(name="示例源", url="https://example.com/feed.xml")


@pytest.fixture
def feed(monkeypatch):
    """Replace the network feed call with a canned entry list."""

    def _install(entries: list[FeedEntry] | Exception):
        def fake_fetch_feed(url: str, timeout: float = 20.0) -> list[FeedEntry]:
            if isinstance(entries, Exception):
                raise entries
            return entries

        monkeypatch.setattr(ingest_service, "fetch_feed", fake_fetch_feed)

    return _install


# --- compute_hash -------------------------------------------------------


def test_compute_hash_is_stable_across_calls():
    first = compute_hash("https://example.com/a", "GPT-5 发布")
    second = compute_hash("https://example.com/a", "GPT-5 发布")

    assert first == second
    assert len(first) == 64


def test_compute_hash_normalizes_case_and_whitespace():
    canonical = compute_hash("https://example.com/a", "GPT-5 Released")

    assert compute_hash("  HTTPS://EXAMPLE.COM/A  ", "GPT-5 Released") == canonical
    assert compute_hash("https://example.com/a", "  gpt-5   released ") == canonical
    assert compute_hash("https://example.com/a", "GPT-5\nReleased") == canonical


def test_compute_hash_differs_on_different_input():
    base = compute_hash("https://example.com/a", "标题")

    assert compute_hash("https://example.com/b", "标题") != base
    assert compute_hash("https://example.com/a", "另一个标题") != base


def test_compute_hash_fits_the_stored_column_width():
    column = RawArticle._meta.get_field("content_hash").max_length

    assert len(compute_hash("https://example.com/a", "标题")) == column


# --- happy path ---------------------------------------------------------


def test_fetch_source_saves_new_articles(source, feed):
    feed([make_entry(1), make_entry(2)])
    fetcher = StubFetcher()

    stats = fetch_source(source, article_fetcher=fetcher)

    assert stats["fetched"] == 2
    assert stats["saved"] == 2
    assert stats["deduped"] == 0
    assert stats["failed"] == 0
    assert RawArticle.objects.count() == 2

    article = RawArticle.objects.get(url="https://example.com/a1")
    assert article.title == "文章 1"
    assert article.summary == "摘要 1"
    assert article.author == "记者"
    assert article.publish_time == PUBLISHED
    assert article.content == "正文内容。"
    assert article.lang == "zh"
    assert article.source == source
    assert article.extract_status == "pending"


def test_fetch_source_records_the_attempt_and_clears_old_errors(source, feed):
    source.last_error = "上次失败了"
    source.save(update_fields=["last_error"])
    feed([make_entry(1)])

    fetch_source(source, article_fetcher=StubFetcher())

    source.refresh_from_db()
    assert source.last_error == ""
    assert source.last_fetched_at is not None


# --- dedup --------------------------------------------------------------


def test_fetch_source_skips_articles_already_stored(source, feed):
    entry = make_entry(1)
    RawArticle.objects.create(
        title=entry.title,
        url=entry.url,
        content="早就抓过了",
        content_hash=compute_hash(entry.url, entry.title),
    )
    feed([entry, make_entry(2)])
    fetcher = StubFetcher()

    stats = fetch_source(source, article_fetcher=fetcher)

    assert stats["fetched"] == 2
    assert stats["saved"] == 1
    assert stats["deduped"] == 1
    assert RawArticle.objects.count() == 2
    # The duplicate must not cost a page fetch.
    assert fetcher.calls == ["https://example.com/a2"]


def test_fetch_source_dedupes_repeats_inside_one_feed(source, feed):
    feed([make_entry(1), make_entry(1)])
    fetcher = StubFetcher()

    stats = fetch_source(source, article_fetcher=fetcher)

    assert stats["saved"] == 1
    assert stats["deduped"] == 1
    assert len(fetcher.calls) == 1


def test_second_run_over_the_same_feed_saves_nothing_new(source, feed):
    feed([make_entry(1), make_entry(2)])

    fetch_source(source, article_fetcher=StubFetcher())
    stats = fetch_source(source, article_fetcher=StubFetcher())

    assert stats["saved"] == 0
    assert stats["deduped"] == 2
    assert RawArticle.objects.count() == 2


# --- failure isolation --------------------------------------------------


def test_one_failed_article_does_not_stop_the_others(source, feed):
    feed([make_entry(1), make_entry(2), make_entry(3)])
    fetcher = StubFetcher(failures={"https://example.com/a2": FetchError("页面 404")})

    stats = fetch_source(source, article_fetcher=fetcher)

    assert stats["saved"] == 2
    assert stats["failed"] == 1
    assert sorted(RawArticle.objects.values_list("url", flat=True)) == [
        "https://example.com/a1",
        "https://example.com/a3",
    ]

    source.refresh_from_db()
    assert "https://example.com/a2" in source.last_error
    assert "页面 404" in source.last_error


def test_unexpected_article_errors_are_contained_too(source, feed):
    feed([make_entry(1), make_entry(2)])
    fetcher = StubFetcher(failures={"https://example.com/a1": RuntimeError("解析器炸了")})

    stats = fetch_source(source, article_fetcher=fetcher)

    assert stats["saved"] == 1
    assert stats["failed"] == 1

    source.refresh_from_db()
    assert "RuntimeError" in source.last_error


def test_feed_level_failure_is_reported_not_raised(source, feed):
    feed(FetchError("feed 拉不动"))

    stats = fetch_source(source, article_fetcher=StubFetcher())

    assert stats == {
        "source": source.name,
        "source_id": source.pk,
        "fetched": 0,
        "deduped": 0,
        "saved": 0,
        "failed": 0,
        "error": "feed 拉不动",
    }
    source.refresh_from_db()
    assert "feed 拉不动" in source.last_error
    assert source.last_fetched_at is not None


def test_overlong_urls_are_skipped_rather_than_truncated(source, feed):
    long_url = "https://example.com/" + "x" * 1200
    feed([FeedEntry(title="超长", url=long_url), make_entry(2)])

    stats = fetch_source(source, article_fetcher=StubFetcher())

    assert stats["saved"] == 1
    assert stats["failed"] == 1
    assert not RawArticle.objects.filter(url=long_url).exists()


# --- fetch_all_enabled --------------------------------------------------


def test_fetch_all_enabled_skips_disabled_sources(db, feed):
    RssSource.objects.create(name="开", url="https://example.com/on.xml", enabled=True)
    RssSource.objects.create(name="关", url="https://example.com/off.xml", enabled=False)
    feed([make_entry(1)])

    totals = fetch_all_enabled(article_fetcher=StubFetcher())

    assert totals["sources"] == 1
    assert totals["saved"] == 1
    assert [stat["source"] for stat in totals["per_source"]] == ["开"]
    assert "elapsed_ms" in totals


def test_fetch_all_enabled_totals_add_up_across_sources(db, monkeypatch):
    first = RssSource.objects.create(name="源 A", url="https://a.example.com/feed.xml")
    RssSource.objects.create(name="源 B", url="https://b.example.com/feed.xml")

    def fake_fetch_feed(url: str, timeout: float = 20.0) -> list[FeedEntry]:
        if url.startswith("https://a."):
            return [make_entry(1), make_entry(2)]
        return [make_entry(3)]

    monkeypatch.setattr(ingest_service, "fetch_feed", fake_fetch_feed)

    totals = fetch_all_enabled(article_fetcher=StubFetcher())

    assert totals["sources"] == 2
    assert totals["fetched"] == 3
    assert totals["saved"] == 3
    assert RawArticle.objects.filter(source=first).count() == 2


def test_one_broken_source_does_not_stop_the_sweep(db, monkeypatch):
    RssSource.objects.create(name="坏源", url="https://bad.example.com/feed.xml")
    RssSource.objects.create(name="好源", url="https://good.example.com/feed.xml")

    def fake_fetch_feed(url: str, timeout: float = 20.0) -> list[FeedEntry]:
        if url.startswith("https://bad."):
            raise FetchError("连接超时")
        return [make_entry(1)]

    monkeypatch.setattr(ingest_service, "fetch_feed", fake_fetch_feed)

    totals = fetch_all_enabled(article_fetcher=StubFetcher())

    assert totals["sources"] == 2
    assert totals["saved"] == 1
    assert RssSource.objects.get(name="坏源").last_error == "连接超时"


def test_a_source_raising_an_unexpected_error_is_contained(db, monkeypatch):
    RssSource.objects.create(name="怪源", url="https://weird.example.com/feed.xml")
    RssSource.objects.create(name="好源", url="https://good.example.com/feed.xml")

    def fake_fetch_feed(url: str, timeout: float = 20.0) -> list[FeedEntry]:
        if url.startswith("https://weird."):
            # Not a FetchError — the kind of thing a parser bug produces, which
            # the per-source `except FetchError` upstream would let through.
            raise MemoryError("feed 太大")
        return [make_entry(1)]

    monkeypatch.setattr(ingest_service, "fetch_feed", fake_fetch_feed)

    totals = fetch_all_enabled(article_fetcher=StubFetcher())

    assert totals["sources"] == 2
    assert totals["saved"] == 1
    broken = next(stat for stat in totals["per_source"] if stat["source"] == "怪源")
    assert broken["error"] == "feed 太大"
    assert "MemoryError" in RssSource.objects.get(name="怪源").last_error


def test_source_ids_narrow_the_sweep(db, feed):
    wanted = RssSource.objects.create(name="要跑的", url="https://a.example.com/feed.xml")
    RssSource.objects.create(name="不跑的", url="https://b.example.com/feed.xml")
    feed([make_entry(1)])

    # The daily job passes this so one broken feed can be re-run on its own
    # without paying to re-fetch every other source.
    totals = fetch_all_enabled(article_fetcher=StubFetcher(), source_ids=[wanted.pk])

    assert totals["sources"] == 1
    assert [stat["source"] for stat in totals["per_source"]] == ["要跑的"]


def test_source_ids_still_exclude_disabled_sources(db, feed):
    disabled = RssSource.objects.create(name="停用", url="https://a.example.com/f.xml", enabled=False)
    feed([make_entry(1)])

    totals = fetch_all_enabled(article_fetcher=StubFetcher(), source_ids=[disabled.pk])

    assert totals["sources"] == 0
    assert RawArticle.objects.count() == 0


def test_an_article_inserted_by_a_concurrent_pass_counts_as_deduped(source, feed):
    """Two passes can pass the existence check before either writes.

    The DB constraint settles it; `fetch_source` has to read that as "already
    had it" rather than as a failure, or a concurrent run would show up on the
    ops panel as a broken feed.
    """
    entry = make_entry(1)
    feed([entry])

    real_create = RawArticle.objects.create

    def create_then_collide(**kwargs):
        real_create(**kwargs)
        raise IntegrityError("duplicate key value violates unique constraint")

    with mock.patch.object(RawArticle.objects, "create", side_effect=create_then_collide):
        stats = fetch_source(source, article_fetcher=StubFetcher())

    assert stats["saved"] == 0
    assert stats["deduped"] == 1
    assert stats["failed"] == 0
    assert RssSource.objects.get(pk=source.pk).last_error == ""
