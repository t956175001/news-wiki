"""Default article fetcher: httpx for transport, trafilatura for main content.

This is the `ArticleFetcher` implementation used in production. The optional
Playwright fetcher (ADR-001) is local-only and slots in behind the same protocol.
"""

import datetime as dt
import json
import logging

import httpx
import trafilatura
from dateutil import parser as date_parser

from apps.common.exceptions import FetchError

from .base import DEFAULT_TIMEOUT, FetchedArticle, build_client, to_aware

logger = logging.getLogger(__name__)


def _parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return to_aware(date_parser.parse(value))
    except (ValueError, OverflowError, TypeError):
        return None


class HttpArticleFetcher:
    """Retrieve a page over HTTP and reduce it to its main text."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    def fetch(self, url: str) -> FetchedArticle:
        html = self._download(url)
        return self._extract(url, html)

    def _download(self, url: str) -> str:
        try:
            with build_client(timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPStatusError as exc:
            raise FetchError(
                f"Article {url} returned HTTP {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"Article {url} could not be retrieved: {exc}") from exc

    def _extract(self, url: str, html: str) -> FetchedArticle:
        # JSON output gets body text and metadata out of a single parse.
        try:
            payload = trafilatura.extract(
                html,
                url=url,
                output_format="json",
                with_metadata=True,
            )
        except Exception as exc:  # trafilatura raises assorted parser errors
            raise FetchError(f"Article {url} could not be parsed: {exc}") from exc

        if not payload:
            raise FetchError(f"Article {url} has no extractable main content")

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise FetchError(f"Article {url} produced unreadable extraction output") from exc

        text = (data.get("text") or "").strip()
        if not text:
            raise FetchError(f"Article {url} has no extractable main content")

        return FetchedArticle(
            url=url,
            title=(data.get("title") or "").strip(),
            content=text,
            summary=(data.get("excerpt") or data.get("description") or "").strip(),
            author=(data.get("author") or "").strip(),
            publish_time=_parse_date(data.get("date")),
            lang=(data.get("language") or "").strip(),
        )
