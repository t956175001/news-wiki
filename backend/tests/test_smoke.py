"""Scaffold smoke tests: the service boots, talks to the DB, and serves docs."""

import pytest


@pytest.mark.django_db
def test_health_returns_ok(client):
    response = client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_openapi_schema_is_generated(client):
    response = client.get("/api/v1/schema/")

    assert response.status_code == 200


def test_swagger_ui_is_served(client):
    response = client.get("/api/v1/docs/")

    assert response.status_code == 200
