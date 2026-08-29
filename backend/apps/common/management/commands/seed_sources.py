"""Seed the default AI-news RSS sources.

Idempotent: sources are matched on `url`. Re-running updates the display name
and site URL but never re-enables a source an operator has switched off.
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


SOURCES: list[SourceSpec] = [
    # Neither Chinese source publishes a usable feed of its own: as of 2026-08-28
    # `https://www.jiqizhixin.com/rss` answers 200 with an HTML page, and 量子位 has
    # no feed endpoint at all. Both URLs below are therefore RSSHub-format
    # placeholders. The public rsshub.app instance answers 403, so point these at a
    # self-hosted RSSHub before expecting articles — until then the sweep records the
    # failure on the source and moves on.
    SourceSpec(
        name="机器之心",
        url="https://rsshub.app/jiqizhixin/all",
        site_url="https://www.jiqizhixin.com/",
        note="RSSHub placeholder — needs a self-hosted instance",
    ),
    SourceSpec(
        name="量子位",
        url="https://rsshub.app/qbitai/all",
        site_url="https://www.qbitai.com/",
        note="RSSHub placeholder — needs a self-hosted instance",
    ),
    SourceSpec(
        name="Hacker News Front Page",
        url="https://hnrss.org/frontpage",
        site_url="https://news.ycombinator.com/",
    ),
    SourceSpec(
        name="arXiv cs.AI",
        url="http://export.arxiv.org/rss/cs.AI",
        site_url="https://arxiv.org/list/cs.AI/recent",
    ),
]


class Command(BaseCommand):
    help = "Seed the default AI-news RSS sources (idempotent)."

    def handle(self, *args, **options) -> None:
        created = 0
        updated = 0

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

        total = RssSource.objects.count()
        enabled = RssSource.objects.filter(enabled=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new, updated {updated}. {total} sources total, {enabled} enabled."
            )
        )
