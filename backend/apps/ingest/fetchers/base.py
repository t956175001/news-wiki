"""Shared fetcher contracts and the one HTTP client every fetcher uses.

Keeping the client here (rather than one per module) means the timeout, the
browser User-Agent and the optional outbound proxy are configured in exactly one
place, and swapping in `playwright.py` later (ADR-001) only means implementing
`ArticleFetcher`.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

import httpx
from django.conf import settings

# Many news sites and feed endpoints answer 403 to a default client UA.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 20.0

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


@dataclass(frozen=True)
class FetchedArticle:
    """One article page after retrieval and main-content extraction."""

    url: str
    title: str = ""
    content: str = ""
    summary: str = ""
    author: str = ""
    publish_time: dt.datetime | None = None
    lang: str = ""


class ArticleFetcher(Protocol):
    """Anything that can turn a URL into a `FetchedArticle`.

    Implementations raise `apps.common.exceptions.FetchError` on failure; they
    never return an empty-content article.
    """

    def fetch(self, url: str) -> FetchedArticle: ...


def build_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.Client:
    """An httpx client with the project's timeout, UA and proxy settings."""
    proxy = getattr(settings, "HTTPS_PROXY", "") or getattr(settings, "HTTP_PROXY", "")
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
        proxy=proxy or None,
    )


def to_aware(value: dt.datetime | None) -> dt.datetime | None:
    """Attach UTC to a naive datetime. Feed and page dates arrive both ways."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value
