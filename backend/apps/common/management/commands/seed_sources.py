"""Seed the default AI-news RSS sources.

Idempotent: sources are matched on `url`. Re-running updates the display name
and site URL but never re-enables a source an operator has switched off.
`RETIRED` is the asymmetric half: those are disabled on *every* run, because
the list is this project's declaration of what it collects and drift away from
it should not outlive the next deploy.

Scope is domestic AI/tech publications. The brief is read by people in China,
and a digest assembled from arXiv abstracts answered a question nobody asked.
Most of these are general tech desks rather than AI ones, so
`apps/ingest/services/relevance.py` filters each item before it is stored.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand

from apps.ingest.models import RssSource


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str
    site_url: str
    note: str = ""


# All six verified answering with parseable items on 2026-08-31.
SOURCES: list[SourceSpec] = [
    SourceSpec(
        name="量子位",
        # D2 recorded that this feed did not exist. It does — the note was
        # written from the RSSHub route failing, not from trying the site's own
        # /feed. It is the only pure-AI source here and the backbone of the
        # digest, so it is also on relevance.ALWAYS_RELEVANT_HOSTS.
        url="https://www.qbitai.com/feed",
        site_url="https://www.qbitai.com/",
        note="纯 AI 源，主力",
    ),
    SourceSpec(
        name="雷峰网",
        url="https://www.leiphone.com/feed",
        site_url="https://www.leiphone.com/",
    ),
    SourceSpec(
        name="InfoQ 中文",
        url="https://www.infoq.cn/feed",
        site_url="https://www.infoq.cn/",
    ),
    SourceSpec(
        name="极客公园",
        url="https://www.geekpark.net/rss",
        site_url="https://www.geekpark.net/",
    ),
    SourceSpec(
        name="IT 之家",
        url="https://www.ithome.com/rss/",
        site_url="https://www.ithome.com/",
        note="量大，靠主题过滤收窄",
    ),
    SourceSpec(
        name="钛媒体",
        url="https://www.tmtpost.com/rss.xml",
        site_url="https://www.tmtpost.com/",
    ),
]

# Kept in the table but switched off. Deleting them would cascade to every
# RawArticle they own, taking the existing demo corpus with it.
RETIRED: list[SourceSpec] = [
    SourceSpec(
        # Not the same row as the 量子位 above: sources are matched on `url`, so
        # replacing the URL in SOURCES created a new row and left this one
        # enabled and failing every sweep. Retiring it by its old URL is what
        # actually retires it.
        name="量子位（旧 RSSHub 路由）",
        url="https://rsshub.app/qbitai/all",
        site_url="https://www.qbitai.com/",
        note="停用：已改用站点自有 feed",
    ),
    SourceSpec(
        name="机器之心",
        # No feed of its own: /rss 302s to an HTML page, and the public
        # rsshub.app instance answers 403/503. Left disabled rather than
        # removed so a self-hosted RSSHub only has to flip `enabled`.
        url="https://rsshub.app/jiqizhixin/all",
        site_url="https://www.jiqizhixin.com/",
        note="停用：无可用 feed，需自建 RSSHub 实例",
    ),
    SourceSpec(
        name="Hacker News Front Page",
        url="https://hnrss.org/frontpage",
        site_url="https://news.ycombinator.com/",
        note="停用：改做国内 AI 简报后不再采集",
    ),
    SourceSpec(
        name="arXiv cs.AI",
        url="http://export.arxiv.org/rss/cs.AI",
        site_url="https://arxiv.org/list/cs.AI/recent",
        note="停用：英文论文与「贴近国内的每日简报」目标不符；历史文章保留",
    ),
]


class Command(BaseCommand):
    help = "Seed the default AI-news RSS sources (idempotent)."

    def handle(self, *args, **options) -> None:
        created = 0
        updated = 0
        retired = 0

        for spec in SOURCES:
            source, was_created = RssSource.objects.get_or_create(
                url=spec.url,
                defaults={"name": spec.name, "site_url": spec.site_url, "enabled": True},
            )
            if was_created:
                created += 1
                suffix = f" — {spec.note}" if spec.note else ""
                self.stdout.write(self.style.SUCCESS(f"+ {spec.name} ({spec.url}){suffix}"))
                continue

            if (source.name, source.site_url) != (spec.name, spec.site_url):
                source.name = spec.name
                source.site_url = spec.site_url
                source.save(update_fields=["name", "site_url"])
                updated += 1
                self.stdout.write(f"~ {spec.name} ({spec.url})")
            else:
                self.stdout.write(f"= {spec.name} ({spec.url})")

        # Disabling is one-directional on purpose: this loop turns sources off,
        # and the loop above only turns one on when it creates it. An operator
        # who re-enables something by hand keeps that decision.
        for spec in RETIRED:
            source = RssSource.objects.filter(url=spec.url, enabled=True).first()
            if source is None:
                continue
            source.enabled = False
            source.save(update_fields=["enabled"])
            retired += 1
            suffix = f" — {spec.note}" if spec.note else ""
            self.stdout.write(self.style.WARNING(f"- {source.name} ({spec.url}){suffix}"))

        total = RssSource.objects.count()
        enabled = RssSource.objects.filter(enabled=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new, updated {updated}, disabled {retired}. "
                f"{total} sources total, {enabled} enabled."
            )
        )
