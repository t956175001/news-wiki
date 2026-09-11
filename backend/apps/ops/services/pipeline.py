"""The daily job: ingest -> extract -> brief, all on one `ExtractionRun`.

One run row, one `step_metrics` dict, one cost figure. The ops panel shows a day
as a single line because a day *is* a single thing, even though three apps did
the work.

Failure policy: a step that fails does not stop the ones after it. Ingest dying
on a dead feed should not cost the site its brief, and an extraction that runs
out of retries should not hide the articles that were already fetched. The run's
final status says how much of it worked:

* `success` — nothing failed (steps with nothing to do count as fine)
* `partial` — something failed and something worked
* `failed`  — nothing worked
"""

import datetime as dt
import logging
import time
from collections.abc import Iterable, Sequence

from django.utils import timezone

from apps.brief.services.generate import STEP_BRIEF, generate_daily_brief
from apps.common.exceptions import AppError, ContentFilteredError, ExtractionStepError
from apps.common.llm import LLMClient
from apps.common.llm.invoke import StepMeta, ms_since
from apps.ingest.fetchers.base import ArticleFetcher
from apps.ingest.models import RawArticle
from apps.ingest.services.ingest import fetch_all_enabled
from apps.ops.models import ExtractionRun
from apps.wiki.services.extract_pipeline import execute_extraction, finish_run, start_run

logger = logging.getLogger(__name__)

# Ingest and brief own one `step_metrics` key each; the extraction phase writes
# four of its own (three steps plus persist), which is why there is no single
# "extract" key here. Shape: ARCHITECTURE 3.3.
STEP_INGEST = "ingest"

# How many pending articles one daily run will extract. A backlog is drained a
# day at a time rather than in one bill: the budget guard is exempt for cron, so
# this constant is the only thing standing between a 500-article backlog and a
# very surprising invoice.
MAX_ARTICLES_PER_RUN = 20

# How long a pending article stays in the queue before it is retired unread.
#
# Ingest brings in several times what one run can extract (measured on the live
# site: ~30-80 articles a day against a ceiling of 20), and the queue is drained
# newest-first. So the oldest pending rows are not "waiting" — they are
# unreachable by construction, and left alone they pile up forever and make the
# backlog look like work in progress. Retiring them says the honest thing: this
# wiki covers the top stories of each day, not every story. See ADR-019.
PENDING_TTL_DAYS = 14

# `ExtractionRun.error_message` is a TextField, but three failed steps should not
# turn one row into a log file.
MAX_ERROR_CHARS = 2000

# How long a run may sit on "running" before the next run declares it abandoned.
#
# A row only leaves "running" when its own thread closes it, so if the process
# dies first — deploy, OOM, an exception that gets past every guard — nothing in
# the system will ever finish it. It then sits at the top of the ops panel and
# every visitor who expands it polls it every 3 seconds, forever. Measured on
# the live site a real run takes 35-110 minutes, so 6h is a wide margin between
# "still working" and "nobody is coming".
ORPHANED_RUN_TTL_HOURS = 6

_OK = {"done", "success", "partial"}
_BAD = {"failed", "partial"}


def _retire_stale_pending(run: ExtractionRun) -> int:
    """Close out pending articles too old to be worth extracting.

    Only ever moves `pending` rows: `extracted` and `failed` are outcomes that
    actually happened and must not be overwritten. Undated articles are left
    alone too — their age is unknown, so nothing follows from it.
    """
    cutoff = timezone.now() - dt.timedelta(days=PENDING_TTL_DAYS)
    retired = RawArticle.objects.filter(
        extract_status="pending", publish_time__isnull=False, publish_time__lt=cutoff
    ).update(extract_status="skipped")
    if retired:
        logger.info(
            "run_id=%s retired %s pending articles older than %sd", run.run_id, retired, PENDING_TTL_DAYS
        )
    return retired


def _pending_articles() -> list[RawArticle]:
    """Newest-first articles that no run has successfully extracted yet."""
    return list(
        RawArticle.objects.filter(extract_status="pending").order_by("-publish_time", "-fetched_at")[
            :MAX_ARTICLES_PER_RUN
        ]
    )


def _record_step(run: ExtractionRun, step: str, metrics: dict) -> None:
    run.step_metrics[step] = metrics
    run.save(update_fields=["step_metrics"])


def _ingest_phase(
    run: ExtractionRun,
    source_ids: Iterable[int] | None,
    article_fetcher: ArticleFetcher | None,
    errors: list[str],
) -> str:
    started = time.monotonic()
    try:
        totals = fetch_all_enabled(article_fetcher=article_fetcher, source_ids=source_ids)
    except Exception as exc:  # noqa: BLE001 - a dead feed must not cost us the brief
        logger.exception("run_id=%s ingest failed", run.run_id)
        errors.append(f"ingest: {exc}")
        _record_step(
            run,
            STEP_INGEST,
            {"status": "failed", "elapsed_ms": ms_since(started), "error_message": str(exc)},
        )
        return "failed"

    metrics = {
        "status": "done",
        "elapsed_ms": totals["elapsed_ms"],
        "fetched": totals["fetched"],
        # Off-topic items dropped before they cost a page fetch. Worth showing:
        # on a general-tech feed it is usually the largest number here, and
        # without it "fetched 60, saved 4" reads like something broke.
        "filtered": totals["filtered"],
        "deduped": totals["deduped"],
        "saved": totals["saved"],
    }
    # Per-article failures inside a source do not fail the step — the sweep
    # already logged them — but they belong on the panel when they happen.
    if totals["failed"]:
        metrics["failed"] = totals["failed"]
    _record_step(run, STEP_INGEST, metrics)
    return "done"


def _extract_phase(
    run: ExtractionRun,
    totals: dict[str, StepMeta],
    errors: list[str],
    *,
    client: LLMClient | None,
    trigger: str,
    sleep,
) -> str:
    _retire_stale_pending(run)
    articles = _pending_articles()
    if not articles:
        logger.info("run_id=%s nothing pending to extract", run.run_id)
        return "skipped"

    try:
        outcome = execute_extraction(run, articles, totals, client=client, trigger=trigger, sleep=sleep)
    except Exception as exc:  # noqa: BLE001 - symmetric with ingest; the brief still has articles
        # `execute_extraction` reports step failures through its outcome, so
        # reaching here means something got past it. That must not cost the day
        # its brief, and it must not escape into `run_daily` either — see the
        # comment on ORPHANED_RUN_TTL_HOURS for what that used to do.
        logger.exception("run_id=%s extraction failed", run.run_id)
        errors.append(f"extract: {exc}")
        return "failed"

    if outcome.error:
        errors.append(f"extract: {outcome.error}")
    return outcome.status


def _brief_phase(
    run: ExtractionRun,
    date: dt.date,
    totals: dict[str, StepMeta],
    errors: list[str],
    *,
    client: LLMClient | None,
    trigger: str,
    sleep,
) -> str:
    started = time.monotonic()
    try:
        _brief, meta = generate_daily_brief(date, run, client=client, trigger=trigger, sleep=sleep)

    except ExtractionStepError as exc:
        spent = StepMeta.from_metrics(exc.metrics)
        totals[STEP_BRIEF] = spent

        if isinstance(exc.cause, ContentFilteredError):
            # The provider read the day's news and declined to summarise it. The
            # extraction it is built on is already saved and every claim on the
            # site remains traceable; losing one day's prose is not worth marking
            # the whole run failed, and no retry would change the answer.
            logger.warning("run_id=%s brief refused by the content filter", run.run_id)
            metrics = spent.as_dict() | {"status": "skipped", "reason": exc.detail}
            _record_step(run, STEP_BRIEF, metrics)
            return "skipped"

        # The model was asked and could not produce usable JSON. Its tokens were
        # still spent, so they go into the same accounting as everything else.
        errors.append(f"brief: {exc.detail}")
        _record_step(run, STEP_BRIEF, spent.as_dict())
        return "failed"

    except AppError as exc:
        if exc.code == "NO_ARTICLES":
            # A day with no articles is not a broken pipeline.
            logger.info("run_id=%s brief skipped: %s", run.run_id, exc.detail)
            _record_step(
                run,
                STEP_BRIEF,
                {"status": "skipped", "elapsed_ms": ms_since(started), "reason": exc.detail},
            )
            return "skipped"

        logger.exception("run_id=%s brief failed", run.run_id)
        errors.append(f"brief: {exc.detail}")
        _record_step(
            run,
            STEP_BRIEF,
            {"status": "failed", "elapsed_ms": ms_since(started), "error_message": exc.detail},
        )
        return "failed"

    totals[STEP_BRIEF] = meta
    _record_step(run, STEP_BRIEF, meta.as_dict())
    return "done"


def _reap_orphaned_runs(run: ExtractionRun) -> int:
    """Close rows whose thread is never coming back. Returns how many.

    Deliberately runs at the start of the daily job rather than on boot: a
    deploy restarts the process, and reaping on boot would shoot a run that is
    still legitimately working in a container that simply restarted alongside.
    """
    cutoff = timezone.now() - dt.timedelta(hours=ORPHANED_RUN_TTL_HOURS)
    orphans = ExtractionRun.objects.filter(status="running", started_at__lt=cutoff).exclude(pk=run.pk)

    reaped = orphans.update(
        status="failed",
        finished_at=timezone.now(),
        error_message=f"abandoned: still running after {ORPHANED_RUN_TTL_HOURS}h, the process that "
        "started it is gone",
    )
    if reaped:
        logger.warning("run_id=%s closed %s orphaned run(s)", run.run_id, reaped)
    return reaped


def _overall(phases: Sequence[str]) -> str:
    """Collapse the per-phase outcomes into the run's status."""
    if not any(phase in _BAD for phase in phases):
        return "success"
    return "partial" if any(phase in _OK for phase in phases) else "failed"


def run_daily(
    source_ids: Iterable[int] | None = None,
    trigger: str = "cron",
    *,
    run: ExtractionRun | None = None,
    date: dt.date | None = None,
    client: LLMClient | None = None,
    article_fetcher: ArticleFetcher | None = None,
    sleep=time.sleep,
) -> ExtractionRun:
    """Fetch today's news, extract it, and write the brief. One run, three phases.

    `run` is accepted rather than always created here so the cron endpoint can
    hand back a `run_id` before any of the work starts.
    """
    started = time.monotonic()
    run = run or start_run(trigger)
    date = date or timezone.localdate()
    logger.info("run_id=%s daily pipeline started (trigger=%s, date=%s)", run.run_id, trigger, date)

    totals: dict[str, StepMeta] = {}
    errors: list[str] = []

    _reap_orphaned_runs(run)

    # Built one at a time, and closed in a `finally`, because every phase
    # handling its own failure is a policy, not a guarantee. When a read timeout
    # got past one on 2026-09-10 the list comprehension never returned, so
    # `finish_run` never ran and the row stayed on "running" for 35 hours.
    phases: list[str] = []
    try:
        phases.append(_ingest_phase(run, source_ids, article_fetcher, errors))
        phases.append(_extract_phase(run, totals, errors, client=client, trigger=trigger, sleep=sleep))
        phases.append(_brief_phase(run, date, totals, errors, client=client, trigger=trigger, sleep=sleep))
    except Exception as exc:
        # Recorded, then re-raised: the background thread logs it, and
        # swallowing it here would hide a bug the guards above should have
        # caught. What must not survive is a row nothing will ever finish.
        phases.append("failed")
        errors.append(f"pipeline: {exc}")
        raise
    finally:
        finish_run(run, totals, _overall(phases), started, "; ".join(errors)[:MAX_ERROR_CHARS])

    logger.info(
        "run_id=%s daily pipeline %s: ingest=%s extract=%s brief=%s, %s tokens, %s CNY",
        run.run_id,
        run.status,
        *phases,
        run.total_tokens,
        run.cost_cny,
    )
    return run
