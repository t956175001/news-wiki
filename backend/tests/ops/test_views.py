"""Ops endpoints: run history and the dashboard's header numbers."""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ops.models import ExtractionRun

pytestmark = pytest.mark.django_db

STEP_METRICS = {
    "ingest": {"status": "done", "elapsed_ms": 4210, "fetched": 12, "deduped": 3, "saved": 9},
    "extract_entities": {
        "status": "done",
        "elapsed_ms": 8300,
        "prompt_tokens": 5120,
        "completion_tokens": 890,
        "count": 24,
        "attempts": 1,
    },
}


@pytest.fixture
def client():
    return APIClient()


def make_run(
    run_id: str,
    *,
    status: str = "success",
    trigger: str = "cron",
    tokens: int = 6010,
    cost: str = "0.0300",
    minutes_ago: int = 0,
    days_ago: int = 0,
) -> ExtractionRun:
    """Create a run at an explicit point in the past.

    `started_at` is set rather than left to `auto_now_add`: the Windows clock has
    ~15ms granularity, so four rows created in a row can share a timestamp and
    any ordering assertion becomes a coin flip.
    """
    run = ExtractionRun.objects.create(
        run_id=run_id,
        status=status,
        trigger=trigger,
        articles_in=9,
        entities_saved=24,
        concepts_saved=11,
        linkages_saved=31,
        prompt_tokens=5120,
        completion_tokens=890,
        total_tokens=tokens,
        cost_cny=Decimal(cost),
        elapsed_ms=28000,
        step_metrics=STEP_METRICS,
        prompt_versions={"wiki.extract_entities": 1},
        finished_at=timezone.now(),
    )
    ExtractionRun.objects.filter(pk=run.pk).update(
        started_at=timezone.now() - dt.timedelta(days=days_ago, minutes=minutes_ago)
    )
    run.refresh_from_db()
    return run


@pytest.fixture
def runs():
    return {
        "success": make_run("a" * 32, minutes_ago=3),
        "partial": make_run("b" * 32, status="partial", trigger="manual", minutes_ago=2),
        "failed": make_run("c" * 32, status="failed", tokens=0, cost="0.0000", minutes_ago=1),
        "old": make_run("d" * 32, days_ago=30, tokens=999999, cost="9.9999"),
    }


# --- runs ---------------------------------------------------------------


def test_the_run_list_is_paginated_newest_first(client, runs):
    body = client.get("/api/v1/ops/runs/").json()

    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 4
    assert body["results"][0]["run_id"] == runs["failed"].run_id


def test_the_run_list_omits_step_metrics(client, runs):
    first = client.get("/api/v1/ops/runs/").json()["results"][0]

    assert "step_metrics" not in first
    assert first["total_tokens"] is not None
    assert first["cost_cny"] is not None


def test_runs_can_be_filtered_by_status_and_trigger(client, runs):
    assert client.get("/api/v1/ops/runs/?status=partial").json()["count"] == 1
    assert client.get("/api/v1/ops/runs/?trigger=manual").json()["count"] == 1


def test_a_run_is_looked_up_by_its_run_id(client, runs):
    body = client.get(f"/api/v1/ops/runs/{runs['success'].run_id}/").json()

    assert body["run_id"] == runs["success"].run_id
    assert body["status"] == "success"
    assert body["articles_in"] == 9
    assert body["linkages_saved"] == 31


def test_the_detail_carries_the_per_step_metrics(client, runs):
    body = client.get(f"/api/v1/ops/runs/{runs['success'].run_id}/").json()

    assert body["step_metrics"]["ingest"]["saved"] == 9
    assert body["step_metrics"]["extract_entities"]["prompt_tokens"] == 5120
    assert body["prompt_versions"] == {"wiki.extract_entities": 1}
    assert body["prompt_tokens"] == 5120
    assert body["completion_tokens"] == 890


def test_a_missing_run_uses_the_error_envelope(client, runs):
    response = client.get(f"/api/v1/ops/runs/{'f' * 32}/")

    assert response.status_code == 404
    assert set(response.json()) == {"code", "detail"}


# --- stats --------------------------------------------------------------


def test_stats_cover_the_last_seven_days(client, runs):
    body = client.get("/api/v1/ops/stats/").json()

    assert body["window_days"] == 7
    assert body["total_runs"] == 3  # the 30-day-old run is outside the window
    assert body["total_tokens"] == 12020
    assert body["total_cost_cny"] == "0.0600"


def test_the_success_rate_counts_only_clean_runs(client, runs):
    body = client.get("/api/v1/ops/stats/").json()

    # One success out of three: partial produced data but lost a step.
    assert body["success_runs"] == 1
    assert body["success_rate"] == pytest.approx(0.3333)
    assert body["by_status"] == {"running": 0, "success": 1, "partial": 1, "failed": 1}


def test_the_window_can_be_widened(client, runs):
    body = client.get("/api/v1/ops/stats/?days=60").json()

    assert body["total_runs"] == 4


def test_stats_with_no_runs_are_zeros_not_nulls(client):
    body = client.get("/api/v1/ops/stats/").json()

    assert body["total_runs"] == 0
    assert body["total_tokens"] == 0
    assert body["total_cost_cny"] == "0.0000"
    assert body["success_rate"] == 0.0


def test_a_bad_days_parameter_uses_the_error_envelope(client):
    assert client.get("/api/v1/ops/stats/?days=abc").json()["code"] == "PARSE_ERROR"
    assert client.get("/api/v1/ops/stats/?days=0").status_code == 400


# --- prompts (D3 endpoints, re-checked against the contract) ------------


def test_prompts_list_carries_the_current_version_text(client):
    body = client.get("/api/v1/prompts/").json()

    keys = {item["key"] for item in body}
    assert "wiki.extract_linkages" in keys
    linkages = next(item for item in body if item["key"] == "wiki.extract_linkages")
    assert linkages["current_version"]["version_no"] >= 1
    assert linkages["current_version"]["text"].strip()
