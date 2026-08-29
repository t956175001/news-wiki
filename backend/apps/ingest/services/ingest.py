"""Pull enabled RSS sources, extract article bodies, and store what is new.

Failure policy: one bad article never stops the source, and one bad source never
stops the sweep. Whatever went wrong is counted, logged, and written to
`RssSource.last_error` so the operator can see it without reading logs.
"""

import hashlib
import logging
import time
from collections.abc import Iterable

from django.db import IntegrityError
from django.utils import timezone

from apps.common.exceptions import FetchError

from ..fetchers.article import HttpArticleFetcher
from ..fetchers.base import ArticleFetcher, FetchedArticle
from ..fetchers.rss import FeedEntry, fetch_feed
from ..models import RawArticle, RssSource

logger = logging.getLogger(__name__)

# `last_error` is a TextField, but a feed with 200 broken items should not turn
# one row into a log file.
MAX_ERROR_CHARS = 2000

_TITLE_MAX = RawArticle._meta.get_field("title").max_length
_URL_MAX = RawArticle._meta.get_field("url").max_length
_AUTHOR_MAX = RawArticle._meta.get_field("author").max_length
_LANG_MAX = RawArticle._meta.get_field("lang").max_length


def compute_hash(url: str, title: str) -> str:
    """Stable dedup key for an article. Contract: ARCHITECTURE section 3.1.

    Normalizing case and collapsing whitespace means the same story re-published
    with cosmetic differences hashes to the same value.
    """
    payload = url.strip().lower() + "|" + " ".join(title.lower().split())
    return hashlib.sha256(payload.encode()).hexdigest()


def _save_article(source: RssSource, entry: FeedEntry, fetched: FetchedArticle, content_hash: str) -> bool:
    """Create the row. Returns False when it was already there.

    The hash is passed in rather than recomputed: it is the same key the caller
    already used to decide this article was worth fetching.
    """
    try:
        RawArticle.objects.create(
            source=source,
            title=(entry.title or fetched.title)[:_TITLE_MAX],
            url=entry.url,
            content=fetched.content,
            summary=entry.summary or fetched.summary,
            author=(entry.author or fetched.author)[:_AUTHOR_MAX],
            publish_time=entry.publish_time or fetched.publish_time,
            content_hash=content_hash,
            lang=fetched.lang[:_LANG_MAX],
        )
    except IntegrityError:
        # Another pass inserted the same hash between the check and the write.
        logger.debug("Article %s already ingested (hash collision on write)", entry.url)
        return False
    return True


def fetch_source(source: RssSource, article_fetcher: ArticleFetcher | None = None) -> dict:
    """Fetch one source end to end and store its new articles.

    Returns `{"source", "source_id", "fetched", "deduped", "saved", "failed"}`,
    plus `"error"` when the feed itself could not be read.
    """
    fetcher = article_fetcher or HttpArticleFetcher()
    stats = {
        "source": source.name,
        "source_id": source.pk,
        "fetched": 0,
        "deduped": 0,
        "saved": 0,
        "failed": 0,
    }

    try:
        entries = fetch_feed(source.url)
    except FetchError as exc:
        logger.warning("Source %s failed: %s", source.name, exc)
        _finish(source, [str(exc)])
        stats["error"] = str(exc)
        return stats

    stats["fetched"] = len(entries)
    errors: list[str] = []
    seen_hashes: set[str] = set()

    for entry in entries:
        if len(entry.url) > _URL_MAX:
            stats["failed"] += 1
            errors.append(f"{entry.url[:120]}...: URL exceeds {_URL_MAX} characters")
            continue

        # Guards against the same story appearing twice inside one feed, which
        # would otherwise cost a page fetch before the DB rejected it.
        content_hash = compute_hash(entry.url, entry.title)
        if content_hash in seen_hashes:
            stats["deduped"] += 1
            continue
        seen_hashes.add(content_hash)

        if RawArticle.objects.filter(content_hash=content_hash).exists():
            stats["deduped"] += 1
            continue

        try:
            fetched = fetcher.fetch(entry.url)
        except FetchError as exc:
            stats["failed"] += 1
            errors.append(f"{entry.url}: {exc}")
            logger.warning("Article %s failed: %s", entry.url, exc)
            continue
        except Exception as exc:  # noqa: BLE001 - one broken page must not end the run
            stats["failed"] += 1
            errors.append(f"{entry.url}: unexpected {type(exc).__name__}: {exc}")
            logger.exception("Article %s raised an unexpected error", entry.url)
            continue

        if _save_article(source, entry, fetched, content_hash):
            stats["saved"] += 1
        else:
            stats["deduped"] += 1

    _finish(source, errors)
    return stats


def fetch_all_enabled(
    article_fetcher: ArticleFetcher | None = None,
    *,
    source_ids: Iterable[int] | None = None,
) -> dict:
    """Sweep every enabled source. Returns the totals plus per-source detail.

    `source_ids` narrows the sweep to specific sources — the daily job takes it
    so one broken feed can be re-run on its own without re-fetching the rest.
    """
    started = time.monotonic()
    fetcher = article_fetcher or HttpArticleFetcher()
    totals = {
        "sources": 0,
        "fetched": 0,
        "deduped": 0,
        "saved": 0,
        "failed": 0,
        "per_source": [],
    }

    sources = RssSource.objects.filter(enabled=True)
    if source_ids is not None:
        sources = sources.filter(pk__in=list(source_ids))

    for source in sources:
        totals["sources"] += 1
        try:
            stats = fetch_source(source, article_fetcher=fetcher)
        except Exception as exc:  # noqa: BLE001 - one broken source must not end the sweep
            logger.exception("Source %s raised an unexpected error", source.name)
            _finish(source, [f"unexpected {type(exc).__name__}: {exc}"])
            stats = {
                "source": source.name,
                "source_id": source.pk,
                "fetched": 0,
                "deduped": 0,
                "saved": 0,
                "failed": 0,
                "error": str(exc),
            }

        for key in ("fetched", "deduped", "saved", "failed"):
            totals[key] += stats[key]
        totals["per_source"].append(stats)

    totals["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    logger.info(
        "Ingest sweep done: %s sources, %s fetched, %s saved, %s deduped, %s failed",
        totals["sources"],
        totals["fetched"],
        totals["saved"],
        totals["deduped"],
        totals["failed"],
    )
    return totals


def _finish(source: RssSource, errors: list[str]) -> None:
    """Stamp the attempt time and replace `last_error` with this run's errors.

    `last_fetched_at` records the attempt, not the success — a source that keeps
    failing should still show when it was last tried.
    """
    source.last_fetched_at = timezone.now()
    source.last_error = "\n".join(errors)[:MAX_ERROR_CHARS]
    source.save(update_fields=["last_fetched_at", "last_error"])
