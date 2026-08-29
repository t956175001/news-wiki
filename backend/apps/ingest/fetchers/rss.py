"""RSS/Atom feed retrieval.

Transport is httpx rather than feedparser's own downloader so that the timeout,
UA and proxy configured in `base.py` apply to feeds as well as article pages;
feedparser is still what parses the bytes.
"""

import datetime as dt
import logging
from dataclasses import dataclass

import feedparser
import httpx

from apps.common.exceptions import FetchError

from .base import DEFAULT_TIMEOUT, build_client, to_aware

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedEntry:
    """One item of a feed, before the article body has been fetched."""

    title: str
    url: str
    summary: str = ""
    author: str = ""
    publish_time: dt.datetime | None = None


def _struct_to_datetime(parsed: tuple | None) -> dt.datetime | None:
    """feedparser hands back a UTC `time.struct_time`, or None."""
    if not parsed:
        return None
    try:
        return dt.datetime(*parsed[:6], tzinfo=dt.UTC)
    except (TypeError, ValueError):
        return None


def _to_entry(raw: dict) -> FeedEntry | None:
    url = (raw.get("link") or "").strip()
    if not url:
        return None
    published = _struct_to_datetime(raw.get("published_parsed")) or _struct_to_datetime(
        raw.get("updated_parsed")
    )
    return FeedEntry(
        title=(raw.get("title") or "").strip(),
        url=url,
        summary=(raw.get("summary") or "").strip(),
        author=(raw.get("author") or "").strip(),
        publish_time=to_aware(published),
    )


def fetch_feed(feed_url: str, timeout: float = DEFAULT_TIMEOUT) -> list[FeedEntry]:
    """Download and parse a feed.

    Raises `FetchError` when the feed cannot be retrieved, or when it cannot be
    parsed into a single usable entry. A feed that parses but is simply empty is
    not an error — it returns `[]`.
    """
    try:
        with build_client(timeout=timeout) as client:
            response = client.get(feed_url)
            response.raise_for_status()
            payload = response.content
    except httpx.HTTPStatusError as exc:
        raise FetchError(
            f"Feed {feed_url} returned HTTP {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"Feed {feed_url} could not be retrieved: {exc}") from exc

    parsed = feedparser.parse(payload)
    entries = [entry for entry in (_to_entry(raw) for raw in parsed.entries) if entry is not None]

    # bozo means malformed XML. feedparser often recovers anyway, so it is only
    # fatal when nothing usable came out of it.
    if parsed.bozo and not entries:
        raise FetchError(f"Feed {feed_url} could not be parsed: {parsed.get('bozo_exception')}")

    logger.info("Fetched %s entries from %s", len(entries), feed_url)
    return entries
