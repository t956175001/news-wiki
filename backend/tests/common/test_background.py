"""The fire-and-forget worker used by the extract and cron endpoints.

Both endpoints return a `run_id` and leave the work to one of these threads, so
the guarantee worth testing is the one the HTTP layer relies on: a task that
raises must not take the process down or leak its database connection, because
nobody is upstream to catch it.
"""

import logging
import threading
from unittest import mock

import pytest

from apps.common import background
from apps.common.background import run_in_background

pytestmark = pytest.mark.django_db


def _raise() -> None:
    raise RuntimeError("boom")


def test_the_task_runs_and_the_caller_does_not_wait():
    done = threading.Event()

    thread = run_in_background("marker", done.set)

    assert done.wait(timeout=5), "background task never ran"
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_arguments_reach_the_task():
    received = {}

    def record(*args, **kwargs):
        received["args"] = args
        received["kwargs"] = kwargs

    run_in_background("with-args", record, 1, "two", key="value").join(timeout=5)

    assert received == {"args": (1, "two"), "kwargs": {"key": "value"}}


def test_the_thread_is_a_daemon_so_it_cannot_hold_the_process_open():
    thread = run_in_background("daemon-check", lambda: None)
    thread.join(timeout=5)

    assert thread.daemon


def test_a_task_that_raises_is_logged_rather_than_lost(caplog):
    def explode():
        raise RuntimeError("extraction fell over")

    with caplog.at_level(logging.ERROR, logger="apps.common.background"):
        run_in_background("boom", explode).join(timeout=5)

    # Threading's default handler would print to stderr and move on; the run row
    # records the failure, and this is for whoever reads the logs.
    assert "Background task boom failed" in caplog.text
    assert "extraction fell over" in caplog.text


@pytest.mark.parametrize(
    ("label", "task"),
    [("ok", lambda: None), ("boom", _raise)],
    ids=["task succeeded", "task raised"],
)
def test_the_database_connection_is_always_closed(monkeypatch, label, task):
    closed = threading.Event()
    monkeypatch.setattr(background, "connection", mock.Mock(close=closed.set))

    run_in_background(label, task).join(timeout=5)

    # Django opens a connection per thread and closes none of them, so the
    # `finally` in `_guarded` is the only thing standing between a daily cron
    # job and a pool full of abandoned connections.
    assert closed.is_set()
