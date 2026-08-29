"""Fire-and-forget worker threads.

ARCHITECTURE section 8.6: extraction is a long task, so the HTTP layer starts it,
returns a `run_id`, and the frontend polls `/api/v1/ops/runs/{run_id}/`. Threads
rather than a task queue — CLAUDE.md rules out Celery and Redis, and a 14-day
project that adds a broker to run one job a day has bought itself a second thing
to deploy, not a feature.

Everything a thread needs to report is already written to `ExtractionRun`, so
nothing here returns a result.
"""

import logging
import threading

from django.db import connection

logger = logging.getLogger(__name__)


def _guarded(label: str, func, args: tuple, kwargs: dict) -> None:
    try:
        func(*args, **kwargs)
    except Exception:  # noqa: BLE001 - nothing upstream can catch this one
        # Threading's default handler prints to stderr and moves on. The run row
        # already records the failure; this is for whoever reads the logs.
        logger.exception("Background task %s failed", label)
    finally:
        # Django opens a connection per thread and closes none of them.
        connection.close()


def run_in_background(label: str, func, *args, **kwargs) -> threading.Thread:
    """Start *func* on a daemon thread and return immediately."""
    thread = threading.Thread(target=_guarded, args=(label, func, args, kwargs), name=label, daemon=True)
    thread.start()
    return thread
