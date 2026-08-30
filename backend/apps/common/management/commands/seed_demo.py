"""Load — or rebuild — the demo dataset.

The public demo has to be worth looking at the moment it loads, and every LLM
call costs real money (DECISIONS.md ADR-014). So the extraction is done once,
here, on a developer's machine, and the *result* is committed as a fixture:

    seed_demo                  # default: loaddata, seconds, no model calls
    seed_demo --live           # really call GLM, then rewrite the fixture

`--live` is a local tool. Nothing on the server should ever run it: it spends
money, it needs the feeds to be reachable, and it takes half an hour.

The fixture deliberately excludes the prompt templates. Those are created by
`apps/common/prompts/migrations/0002_seed_prompts.py`, so shipping them here as
well would mean two sources of truth for the same four rows.
"""

import datetime as dt
import json
import logging
import time
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.brief.models import DailyBrief
from apps.brief.services.generate import generate_daily_brief
from apps.common.exceptions import AppError
from apps.ingest.models import RawArticle, RssSource
from apps.ingest.services.ingest import fetch_all_enabled
from apps.ops.models import ExtractionRun
from apps.wiki.models import Concept, Entity, Evidence, Linkage
from apps.wiki.services.extract_pipeline import run_extraction

logger = logging.getLogger(__name__)

# Dumped in dependency order so `loaddata` never meets a forward reference.
FIXTURE_APPS = ["ingest", "ops", "wiki", "brief"]

DEFAULT_FIXTURE = Path(settings.BASE_DIR) / "fixtures" / "demo.json"

# PRD section 3: 80-100 extracted articles.
DEFAULT_TARGET_ARTICLES = 100

# One `ExtractionRun` per calendar day of material, so the ops panel has a
# plausible history to show rather than one enormous row.
DEFAULT_MIN_BRIEF_DAYS = 7


class Command(BaseCommand):
    help = "Load the demo dataset from its fixture, or rebuild it with real LLM calls."

    def add_arguments(self, parser) -> None:
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--from-fixture",
            action="store_true",
            help="Load backend/fixtures/demo.json. The default; no model calls, no network.",
        )
        mode.add_argument(
            "--live",
            action="store_true",
            help="Fetch, extract and summarise for real, then rewrite the fixture. Local only.",
        )
        parser.add_argument(
            "--fixture",
            default=str(DEFAULT_FIXTURE),
            help=f"Fixture path to read or write (default: {DEFAULT_FIXTURE}).",
        )
        parser.add_argument(
            "--articles",
            type=int,
            default=DEFAULT_TARGET_ARTICLES,
            help=f"--live: how many articles to extract (default: {DEFAULT_TARGET_ARTICLES}).",
        )
        parser.add_argument(
            "--budget-cny",
            type=float,
            default=None,
            help=(
                "--live: raise the daily spend cap for this process only. The default cap is "
                "sized for visitor traffic and a full rebuild will trip it."
            ),
        )
        parser.add_argument(
            "--spread-days",
            type=int,
            default=0,
            help=(
                "--live: re-date the articles evenly across this many days so the brief archive "
                "has a history. Demo data only — it makes stored publish times disagree with the "
                "source pages. 0 (default) keeps the dates the feeds gave."
            ),
        )
        parser.add_argument(
            "--keep-existing",
            action="store_true",
            help="--live: extract on top of what is already in the database instead of clearing it.",
        )

    def handle(self, *args, **options) -> None:
        if options["live"]:
            self._live(options)
        else:
            self._from_fixture(Path(options["fixture"]))

        self._report_counts()

    # --- default mode ---------------------------------------------------

    def _from_fixture(self, path: Path) -> None:
        if not path.exists():
            raise CommandError(
                f"{path} not found. It is committed to the repository — if it is missing, "
                f"either the checkout is incomplete or you meant to run --live."
            )

        started = time.monotonic()
        # `loaddata` upserts on primary key, so re-running is safe and a partial
        # database ends up consistent with the fixture rather than merged with it.
        call_command("loaddata", str(path), verbosity=0)
        self.stdout.write(self.style.SUCCESS(f"Loaded {path.name} in {time.monotonic() - started:.1f}s"))

    # --- rebuild mode ---------------------------------------------------

    def _live(self, options: dict) -> None:
        if options["budget_cny"] is not None:
            # Process-local, not persisted: the cap that protects the public
            # site from visitor traffic is not the cap for an operator who typed
            # this command on purpose.
            settings.LLM_DAILY_BUDGET_CNY = options["budget_cny"]

        self.stdout.write(self.style.WARNING("--live makes real GLM calls and costs real money."))

        if not options["keep_existing"]:
            self._clear()

        self._ensure_sources()
        self._ingest()
        runs = self._extract(options["articles"], options["spread_days"])
        # Before the briefs, not after: `generate_daily_brief` picks its material
        # from every article dated that day, so pruning afterwards would leave
        # citations pointing at rows that are no longer in the fixture.
        self._prune()
        self._write_briefs(runs)
        self._dump(Path(options["fixture"]))

    def _clear(self) -> None:
        """Start from empty so the fixture is a clean dataset, not an accretion."""
        with transaction.atomic():
            for model in (Evidence, Linkage, Concept, Entity, DailyBrief, ExtractionRun, RawArticle):
                model.objects.all().delete()
        self.stdout.write("Cleared previous demo data.")

    def _ensure_sources(self) -> None:
        if not RssSource.objects.filter(enabled=True).exists():
            call_command("seed_sources", verbosity=0)
        enabled = RssSource.objects.filter(enabled=True).count()
        self.stdout.write(f"{enabled} enabled source(s).")

    def _ingest(self) -> None:
        started = time.monotonic()
        totals = fetch_all_enabled()
        self.stdout.write(
            f"Ingest: {totals['saved']} saved, {totals['deduped']} deduped, "
            f"{totals['failed']} failed, in {time.monotonic() - started:.0f}s"
        )
        for stat in totals["per_source"]:
            if stat.get("error"):
                self.stdout.write(self.style.WARNING(f"  ! {stat['source']}: {stat['error']}"))

    def _spread(self, articles: list[RawArticle], days: int) -> None:
        """Re-date *articles* evenly across the last *days* days. Demo data only.

        The feeds carry one day of news: an arXiv listing announces today's
        papers and the HN front page is today's front page. A one-day dataset
        would leave the brief archive and the ops history with a single row
        each, which shows none of what those pages do.

        This rewrites `publish_time` and therefore makes the stored date
        disagree with the source page. That is a real cost, paid deliberately
        and only in seeded demo data: `--live` is never run on the server, and
        the URL, title, body and every evidence snippet stay exactly as fetched,
        so the traceability the project is selling is untouched.
        """
        today = timezone.localdate()
        per_day = -(-len(articles) // days)  # ceiling: fill each day before moving on

        for index, article in enumerate(articles):
            # Newest articles land on the most recent days, so the archive still
            # reads in the order the stories actually arrived.
            stamp = article.publish_time or article.fetched_at
            local = timezone.localtime(stamp)
            target_day = today - dt.timedelta(days=index // per_day)
            article.publish_time = local.replace(
                year=target_day.year, month=target_day.month, day=target_day.day
            )

        RawArticle.objects.bulk_update(articles, ["publish_time"])
        self.stdout.write(
            self.style.WARNING(
                f"Re-dated {len(articles)} article(s) across {days} day(s) for the demo archive; "
                f"stored publish times no longer match the source pages."
            )
        )

    def _extract(self, target: int, spread_days: int) -> list[tuple[dt.date, ExtractionRun]]:
        """Extract up to *target* articles, one run per publication day.

        Grouped by day rather than sliced into equal batches because that is how
        the pipeline runs in production — one cron job per day — and the ops
        panel should show the shape of the real thing.
        """
        articles = list(
            RawArticle.objects.filter(extract_status="pending").order_by("-publish_time", "-fetched_at")[
                :target
            ]
        )
        if not articles:
            raise CommandError("Nothing pending to extract. Are the feeds reachable?")

        if spread_days:
            self._spread(articles, spread_days)

        by_day: dict[dt.date, list[RawArticle]] = {}
        for article in articles:
            by_day.setdefault(self._day_of(article), []).append(article)

        self.stdout.write(f"Extracting {len(articles)} article(s) across {len(by_day)} day(s).")

        runs = []
        for day in sorted(by_day):
            batch = by_day[day]
            started = time.monotonic()
            run = run_extraction(batch, trigger="seed")
            runs.append((day, run))
            self.stdout.write(
                f"  {day}: {len(batch):>3} article(s) -> {run.status}, "
                f"{run.entities_saved} entities / {run.concepts_saved} concepts / "
                f"{run.linkages_saved} linkages, {run.total_tokens} tokens, "
                f"{run.cost_cny} CNY, {time.monotonic() - started:.0f}s"
            )
            if run.error_message:
                self.stdout.write(self.style.WARNING(f"      {run.error_message[:200]}"))
        return runs

    def _write_briefs(self, runs: list[tuple[dt.date, ExtractionRun]]) -> None:
        """One brief per day that has articles, dated to that day.

        Each day's brief is generated from that day's own articles and linked to
        the run that extracted them, so the archive reads like a site that has
        been running for a week rather than one that wrote seven briefs in an
        afternoon.
        """
        written = 0
        for day, run in runs:
            try:
                brief, meta = generate_daily_brief(day, run, trigger="seed")
            except AppError as exc:
                self.stdout.write(self.style.WARNING(f"  {day}: brief skipped ({exc.code})"))
                continue
            written += 1
            self.stdout.write(f"  {day}: {brief.title} ({meta.count} citation(s))")

        self.stdout.write(f"Briefs: {written} written.")
        if written < DEFAULT_MIN_BRIEF_DAYS:
            self.stdout.write(
                self.style.WARNING(
                    f"Only {written} day(s) of briefs; the PRD asks for {DEFAULT_MIN_BRIEF_DAYS}. "
                    f"The feeds did not carry enough days of material."
                )
            )

    def _prune(self) -> int:
        """Drop articles the extraction never reached, so the fixture is one dataset.

        A sweep brings back far more than `--articles` asks for, and the surplus
        would otherwise ship as rows with no entities, no evidence and nothing to
        show — padding the article list and, worse, offering the brief material
        it never summarised.
        """
        leftovers = RawArticle.objects.exclude(extract_status="extracted")
        count = leftovers.count()
        if count:
            leftovers.delete()
            self.stdout.write(f"Pruned {count} article(s) that were never extracted.")
        return count

    def _dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        # Captured and written here rather than via `dumpdata --output`, which
        # opens the file in the locale encoding. On a Chinese Windows box that
        # is GBK, and the fixture would arrive in the repository unreadable to
        # CI and to the server.
        buffer = StringIO()
        call_command("dumpdata", *FIXTURE_APPS, indent=1, stdout=buffer, verbosity=0)
        payload = buffer.getvalue()
        path.write_text(payload, encoding="utf-8", newline="\n")

        records = len(json.loads(payload))
        size_mb = path.stat().st_size / 1_048_576
        self.stdout.write(self.style.SUCCESS(f"Wrote {path} — {records} records, {size_mb:.1f} MB"))

    @staticmethod
    def _day_of(article: RawArticle) -> dt.date:
        """The day a brief would file this article under.

        Mirrors `_articles_for` in the brief service: publish time when the feed
        gave one, arrival time when it did not.
        """
        stamp = article.publish_time or article.fetched_at
        return timezone.localtime(stamp).date()

    # --- shared ---------------------------------------------------------

    def _report_counts(self) -> None:
        rows = [
            ("sources", RssSource.objects.count()),
            ("articles", RawArticle.objects.count()),
            ("entities", Entity.objects.count()),
            ("concepts", Concept.objects.count()),
            ("linkages", Linkage.objects.count()),
            ("evidences", Evidence.objects.count()),
            ("briefs", DailyBrief.objects.count()),
            ("runs", ExtractionRun.objects.count()),
        ]
        width = max(len(name) for name, _ in rows)
        for name, count in rows:
            self.stdout.write(f"  {name:<{width}}  {count}")
