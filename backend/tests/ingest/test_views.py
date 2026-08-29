"""Ingest endpoints: sources and raw articles."""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ingest.models import RawArticle, RssSource

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def feed():
    source = RssSource.objects.create(name="机器之心", url="https://example.com/feed")
    other = RssSource.objects.create(name="Import AI", url="https://example.com/other", enabled=False)
    RawArticle.objects.create(
        source=source,
        title="OpenAI 发布 GPT-5",
        url="https://example.com/gpt5",
        content="正文" * 100,
        content_hash="ingest-view-0001",
        publish_time=timezone.now(),
        extract_status="extracted",
    )
    RawArticle.objects.create(
        source=other,
        title="Anthropic 的新论文",
        url="https://example.com/paper",
        content="另一篇正文",
        content_hash="ingest-view-0002",
        publish_time=timezone.now(),
    )
    return {"source": source, "other": other}


# --- sources ------------------------------------------------------------


def test_sources_list_with_article_counts(client, feed):
    body = client.get("/api/v1/ingest/sources/").json()

    assert len(body) == 2  # unpaginated
    by_name = {item["name"]: item for item in body}
    assert by_name["机器之心"]["article_count"] == 1
    assert by_name["Import AI"]["enabled"] is False


def test_a_source_can_be_added(client):
    response = client.post(
        "/api/v1/ingest/sources/",
        {"name": "新源", "url": "https://example.com/new-feed"},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["enabled"] is True
    assert RssSource.objects.filter(name="新源").exists()


def test_adding_a_duplicate_source_uses_the_error_envelope(client, feed):
    response = client.post(
        "/api/v1/ingest/sources/",
        {"name": "重复", "url": feed["source"].url},
        format="json",
    )

    assert response.status_code == 400
    assert set(response.json()) >= {"code", "detail"}
    assert "url" in response.json()["fields"]


def test_adding_a_source_spends_the_demo_quota(client, settings):
    settings.DEMO_MODE = True
    settings.DEMO_WRITE_RATE = "2/day"

    codes = [
        client.post(
            "/api/v1/ingest/sources/",
            {"name": f"源{index}", "url": f"https://example.com/feed-{index}"},
            format="json",
        ).status_code
        for index in range(3)
    ]

    assert codes == [201, 201, 429]


def test_listing_sources_does_not_spend_the_quota(client, feed, settings):
    settings.DEMO_MODE = True
    settings.DEMO_WRITE_RATE = "1/day"

    codes = [client.get("/api/v1/ingest/sources/").status_code for _ in range(4)]

    assert codes == [200] * 4


# --- articles -----------------------------------------------------------


def test_articles_list_is_paginated_and_omits_the_body(client, feed):
    body = client.get("/api/v1/ingest/articles/").json()

    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 2
    assert "content" not in body["results"][0]
    assert body["results"][0]["source_name"] in {"机器之心", "Import AI"}


def test_articles_can_be_filtered_by_source(client, feed):
    body = client.get(f"/api/v1/ingest/articles/?source={feed['source'].pk}").json()

    assert [item["title"] for item in body["results"]] == ["OpenAI 发布 GPT-5"]


def test_articles_can_be_filtered_by_extract_status(client, feed):
    body = client.get("/api/v1/ingest/articles/?extract_status=pending").json()

    assert [item["title"] for item in body["results"]] == ["Anthropic 的新论文"]


def test_articles_search_matches_the_title(client, feed):
    body = client.get("/api/v1/ingest/articles/?search=GPT-5").json()

    assert body["count"] == 1


def test_article_detail_carries_the_full_text(client, feed):
    article = RawArticle.objects.get(content_hash="ingest-view-0001")

    body = client.get(f"/api/v1/ingest/articles/{article.pk}/").json()

    assert body["content"] == article.content
    assert body["content_hash"] == "ingest-view-0001"


def test_a_missing_article_uses_the_error_envelope(client):
    response = client.get("/api/v1/ingest/articles/999999/")

    assert response.status_code == 404
    assert set(response.json()) == {"code", "detail"}


def test_page_size_can_be_set(client, feed):
    body = client.get("/api/v1/ingest/articles/?page_size=1").json()

    assert len(body["results"]) == 1
    assert body["next"] is not None
