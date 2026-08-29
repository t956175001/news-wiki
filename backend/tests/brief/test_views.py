"""Brief endpoints: archive list, latest issue, one issue by date."""

import datetime as dt

import pytest
from rest_framework.test import APIClient

from apps.brief.models import DailyBrief
from apps.ops.models import ExtractionRun

pytestmark = pytest.mark.django_db

CITATIONS = [
    {
        "index": 1,
        "raw_article_id": 42,
        "title": "OpenAI 发布 GPT-5",
        "url": "https://example.com/gpt5",
        "publish_time": "2026-08-27T10:00:00+00:00",
    }
]


@pytest.fixture
def client():
    return APIClient()


def make_brief(date: dt.date, *, title: str = "今日 AI 简报", run=None) -> DailyBrief:
    return DailyBrief.objects.create(
        date=date,
        title=title,
        content_md="OpenAI 发布了 GPT-5[1]。",
        citations=CITATIONS,
        model_name="glm-4.7",
        extraction_run=run,
    )


@pytest.fixture
def briefs():
    run = ExtractionRun.objects.create(run_id="b" * 32, trigger="cron", status="success")
    older = make_brief(dt.date(2026, 8, 27), title="前天的简报")
    newest = make_brief(dt.date(2026, 8, 29), title="今天的简报", run=run)
    return {"older": older, "newest": newest, "run": run}


# --- list ---------------------------------------------------------------


def test_the_list_is_paginated_newest_first(client, briefs):
    body = client.get("/api/v1/brief/").json()

    assert set(body) == {"count", "next", "previous", "results"}
    assert [item["date"] for item in body["results"]] == ["2026-08-29", "2026-08-27"]


def test_the_list_omits_the_body_but_counts_citations(client, briefs):
    first = client.get("/api/v1/brief/").json()["results"][0]

    assert "content_md" not in first
    assert "citations" not in first
    assert first["citation_count"] == 1


# --- latest -------------------------------------------------------------


def test_latest_returns_the_newest_issue_in_full(client, briefs):
    body = client.get("/api/v1/brief/latest/").json()

    assert body["date"] == "2026-08-29"
    assert body["title"] == "今天的简报"
    assert body["content_md"] == "OpenAI 发布了 GPT-5[1]。"
    assert body["model_name"] == "glm-4.7"
    assert body["run_id"] == briefs["run"].run_id


def test_latest_carries_the_citation_fields_the_page_renders(client, briefs):
    citation = client.get("/api/v1/brief/latest/").json()["citations"][0]

    assert set(citation) == {"index", "raw_article_id", "title", "url", "publish_time"}
    assert citation["url"] == "https://example.com/gpt5"


def test_latest_without_any_brief_uses_the_error_envelope(client):
    response = client.get("/api/v1/brief/latest/")

    assert response.status_code == 404
    assert response.json()["code"] == "NO_BRIEF"


def test_a_brief_with_no_run_reports_a_null_run_id(client):
    make_brief(dt.date(2026, 8, 29))

    assert client.get("/api/v1/brief/latest/").json()["run_id"] is None


# --- by date ------------------------------------------------------------


def test_a_brief_can_be_fetched_by_date(client, briefs):
    body = client.get("/api/v1/brief/2026-08-27/").json()

    assert body["title"] == "前天的简报"


def test_a_date_with_no_brief_is_a_404(client, briefs):
    response = client.get("/api/v1/brief/2026-01-01/")

    assert response.status_code == 404
    assert set(response.json()) == {"code", "detail"}


def test_latest_is_not_swallowed_by_the_date_route(client, briefs):
    """`latest` cannot match the date pattern, so route order cannot break this."""
    assert client.get("/api/v1/brief/latest/").json()["date"] == "2026-08-29"


def test_a_malformed_date_does_not_reach_the_view(client, briefs):
    assert client.get("/api/v1/brief/not-a-date/").status_code == 404


def test_a_date_shaped_but_impossible_value_is_rejected(client, briefs):
    response = client.get("/api/v1/brief/2026-02-31/")

    assert response.status_code == 400
    assert response.json()["code"] == "PARSE_ERROR"
