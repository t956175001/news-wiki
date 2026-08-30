"""Fetcher tests. Every HTTP call is served by `httpx_mock` — nothing goes out.

trafilatura and feedparser themselves are exercised for real; only the transport
is faked, so a change in extraction behaviour will actually show up here.
"""

import datetime as dt
import json
from types import SimpleNamespace

import httpx
import pytest

from apps.common.exceptions import FetchError
from apps.ingest.fetchers.article import HttpArticleFetcher
from apps.ingest.fetchers.base import DEFAULT_TIMEOUT, USER_AGENT, build_client
from apps.ingest.fetchers.rss import fetch_feed

ARTICLE_URL = "https://example.com/news/gpt5"

ARTICLE_HTML = """<!doctype html>
<html lang="en">
  <head>
    <title>GPT-5 released</title>
    <meta name="author" content="Jane Doe">
    <meta property="article:published_time" content="2026-08-27T10:00:00Z">
  </head>
  <body>
    <nav><a href="/">Home</a><a href="/subscribe">Subscribe to our newsletter</a></nav>
    <article>
      <h1>GPT-5 released</h1>
      <p>OpenAI announced the model today at a press event in San Francisco,
         describing it as the largest jump in reasoning ability it has shipped.</p>
      <p>The company said the system improves benchmark scores substantially over
         the previous generation, and that it will reach API customers next month.</p>
    </article>
    <footer>Copyright 2026. All rights reserved.</footer>
  </body>
</html>
"""

FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example AI News</title>
    <link>https://example.com/</link>
    <item>
      <title>GPT-5 发布</title>
      <link>https://example.com/news/gpt5</link>
      <description>OpenAI 今天发布了 GPT-5。</description>
      <pubDate>Thu, 27 Aug 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>另一条新闻</title>
      <link>https://example.com/news/other</link>
      <description>摘要二</description>
    </item>
    <item>
      <title>没有链接的条目</title>
      <description>应当被丢掉</description>
    </item>
  </channel>
</rss>
"""

FEED_URL = "https://example.com/feed.xml"


# --- article fetcher ----------------------------------------------------


def test_article_fetcher_extracts_main_content(httpx_mock):
    httpx_mock.add_response(url=ARTICLE_URL, html=ARTICLE_HTML)

    article = HttpArticleFetcher().fetch(ARTICLE_URL)

    assert "OpenAI announced the model today" in article.content
    assert "improves benchmark scores" in article.content
    # Chrome and footer boilerplate must not survive extraction.
    assert "Subscribe to our newsletter" not in article.content
    assert "All rights reserved" not in article.content
    assert article.url == ARTICLE_URL
    assert article.title == "GPT-5 released"
    assert article.author == "Jane Doe"
    assert article.publish_time == dt.datetime(2026, 8, 27, tzinfo=dt.UTC)


def test_article_fetcher_sends_a_browser_user_agent(httpx_mock):
    httpx_mock.add_response(url=ARTICLE_URL, html=ARTICLE_HTML)

    HttpArticleFetcher().fetch(ARTICLE_URL)

    request = httpx_mock.get_requests()[0]
    assert request.headers["User-Agent"] == USER_AGENT
    assert "Mozilla/5.0" in request.headers["User-Agent"]


def test_article_fetcher_raises_fetch_error_on_http_error(httpx_mock):
    httpx_mock.add_response(url=ARTICLE_URL, status_code=500)

    with pytest.raises(FetchError) as excinfo:
        HttpArticleFetcher().fetch(ARTICLE_URL)

    assert "500" in str(excinfo.value)
    assert excinfo.value.code == "FETCH_ERROR"


def test_article_fetcher_raises_fetch_error_on_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"))

    with pytest.raises(FetchError):
        HttpArticleFetcher().fetch(ARTICLE_URL)


def test_article_fetcher_raises_fetch_error_when_there_is_no_body(httpx_mock):
    httpx_mock.add_response(url=ARTICLE_URL, html="<html><head><title>t</title></head><body></body></html>")

    with pytest.raises(FetchError) as excinfo:
        HttpArticleFetcher().fetch(ARTICLE_URL)

    assert "main content" in str(excinfo.value)


def test_client_timeout_is_twenty_seconds():
    with build_client() as client:
        assert DEFAULT_TIMEOUT == 20.0
        assert client.timeout.read == 20.0
        assert client.timeout.connect == 20.0


# --- feed fetcher -------------------------------------------------------


def test_fetch_feed_parses_entries(httpx_mock):
    httpx_mock.add_response(url=FEED_URL, text=FEED_XML, headers={"Content-Type": "application/xml"})

    entries = fetch_feed(FEED_URL)

    # The item without a <link> is dropped: there is nothing to fetch or dedup on.
    assert len(entries) == 2
    first = entries[0]
    assert first.title == "GPT-5 发布"
    assert first.url == "https://example.com/news/gpt5"
    assert first.summary == "OpenAI 今天发布了 GPT-5。"
    assert first.publish_time == dt.datetime(2026, 8, 27, 10, 0, tzinfo=dt.UTC)
    # An item with no pubDate is still usable.
    assert entries[1].publish_time is None


def test_fetch_feed_sends_a_browser_user_agent(httpx_mock):
    httpx_mock.add_response(url=FEED_URL, text=FEED_XML)

    fetch_feed(FEED_URL)

    assert httpx_mock.get_requests()[0].headers["User-Agent"] == USER_AGENT


def test_fetch_feed_raises_fetch_error_on_http_error(httpx_mock):
    httpx_mock.add_response(url=FEED_URL, status_code=404)

    with pytest.raises(FetchError) as excinfo:
        fetch_feed(FEED_URL)

    assert "404" in str(excinfo.value)


def test_fetch_feed_raises_fetch_error_on_connect_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("no route to host"))

    with pytest.raises(FetchError):
        fetch_feed(FEED_URL)


def test_fetch_feed_raises_fetch_error_on_unparseable_body(httpx_mock):
    httpx_mock.add_response(url=FEED_URL, text="this is definitely not a feed <<<>>>")

    with pytest.raises(FetchError) as excinfo:
        fetch_feed(FEED_URL)

    assert "could not be parsed" in str(excinfo.value)


def test_fetch_feed_returns_empty_list_for_a_feed_with_no_items(httpx_mock):
    empty = '<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
    httpx_mock.add_response(url=FEED_URL, text=empty)

    assert fetch_feed(FEED_URL) == []


def test_an_unparseable_pubdate_leaves_the_entry_undated(httpx_mock):
    """A bad date costs the date, not the article."""
    feed = FEED_XML.replace(
        "<pubDate>Thu, 27 Aug 2026 10:00:00 GMT</pubDate>",
        "<pubDate>下周三下午</pubDate>",
    )
    httpx_mock.add_response(url=FEED_URL, text=feed)

    entries = fetch_feed(FEED_URL)

    assert entries[0].url == "https://example.com/news/gpt5"
    assert entries[0].publish_time is None


@pytest.mark.parametrize(
    "struct",
    [(2026, 13, 32, 25, 61, 61, 0, 0, 0), ("2026", "08", "27", 0, 0, 0, 0, 0, 0)],
    ids=["out of range", "strings"],
)
def test_a_nonsensical_parsed_date_leaves_the_entry_undated(httpx_mock, monkeypatch, struct):
    """feedparser can hand back a `struct_time` that `datetime` refuses.

    Month 13 exists in the wild. The article is still worth ingesting — the
    brief dates an undated article by `fetched_at` instead.
    """
    httpx_mock.add_response(url=FEED_URL, text=FEED_XML)
    parsed = SimpleNamespace(
        entries=[{"link": "https://example.com/news/gpt5", "title": "t", "published_parsed": struct}],
        bozo=False,
    )
    monkeypatch.setattr("apps.ingest.fetchers.rss.feedparser.parse", lambda payload: parsed)

    entries = fetch_feed(FEED_URL)

    assert entries[0].publish_time is None


# --- article fetcher: parsing failures -----------------------------------


def test_article_fetcher_reports_a_parser_crash_as_a_fetch_error(httpx_mock, monkeypatch):
    httpx_mock.add_response(url=ARTICLE_URL, html=ARTICLE_HTML)

    def _explode(*args, **kwargs):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr("apps.ingest.fetchers.article.trafilatura.extract", _explode)

    # trafilatura raises assorted parser errors on malformed markup. One bad
    # page must arrive at `fetch_source` as a FetchError like any other, or the
    # sweep's per-article isolation does not apply to it.
    with pytest.raises(FetchError) as excinfo:
        HttpArticleFetcher().fetch(ARTICLE_URL)

    assert "could not be parsed" in str(excinfo.value)


def test_article_fetcher_reports_unreadable_extraction_output(httpx_mock, monkeypatch):
    httpx_mock.add_response(url=ARTICLE_URL, html=ARTICLE_HTML)
    monkeypatch.setattr(
        "apps.ingest.fetchers.article.trafilatura.extract",
        lambda *args, **kwargs: "{not json",
    )

    with pytest.raises(FetchError) as excinfo:
        HttpArticleFetcher().fetch(ARTICLE_URL)

    assert "unreadable extraction output" in str(excinfo.value)


def test_article_fetcher_rejects_a_page_whose_body_is_only_whitespace(httpx_mock, monkeypatch):
    httpx_mock.add_response(url=ARTICLE_URL, html=ARTICLE_HTML)
    monkeypatch.setattr(
        "apps.ingest.fetchers.article.trafilatura.extract",
        lambda *args, **kwargs: '{"text": "   \\n  ", "title": "t"}',
    )

    # An article of pure whitespace would reach the corpus as a blank block and
    # cost a model call to say nothing.
    with pytest.raises(FetchError) as excinfo:
        HttpArticleFetcher().fetch(ARTICLE_URL)

    assert "main content" in str(excinfo.value)


@pytest.mark.parametrize("value", ["", None, "not a date at all", "2026-13-45T99:99:99"])
def test_an_unparseable_article_date_is_dropped_not_fatal(httpx_mock, monkeypatch, value):
    httpx_mock.add_response(url=ARTICLE_URL, html=ARTICLE_HTML)
    payload = json.dumps({"text": "正文足够长，可以入库。", "title": "标题", "date": value})
    monkeypatch.setattr(
        "apps.ingest.fetchers.article.trafilatura.extract",
        lambda *args, **kwargs: payload,
    )

    fetched = HttpArticleFetcher().fetch(ARTICLE_URL)

    assert fetched.publish_time is None
    assert fetched.content == "正文足够长，可以入库。"
