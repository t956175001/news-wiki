"""The per-IP ceiling on the read API.

The read endpoints spend no tokens, so this is not a cost guard rail — it is a
capacity one. `/wiki/graph/` is four aggregate queries against three gunicorn
workers, and nothing else stands between it and a loop with `curl` in it.
"""

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

URL = "/api/v1/wiki/entities/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def low_rate(settings):
    """Three requests is enough to prove the mechanism; 120 would be slow."""
    settings.READ_RATE = "3/min"


def test_the_fourth_read_of_the_minute_is_refused(client):
    codes = [client.get(URL).status_code for _ in range(4)]

    assert codes == [200, 200, 200, 429]


def test_the_ceiling_is_per_ip(client):
    for _ in range(3):
        client.get(URL)

    other_visitor = client.get(URL, REMOTE_ADDR="10.0.0.42")

    assert other_visitor.status_code == 200


def test_an_empty_rate_disables_the_ceiling(client, settings):
    settings.READ_RATE = ""

    codes = [client.get(URL).status_code for _ in range(6)]

    assert codes == [200] * 6


def test_the_write_endpoint_keeps_its_own_stricter_quota(client, settings):
    """`ExtractView` declares `throttle_classes`, which replaces the default.

    Worth pinning: if someone later switches it to *adding* the global class,
    the demo quota would start sharing a counter with ordinary browsing.
    """
    settings.READ_RATE = "1/min"

    # Four reads would be refused at 1/min; the write endpoint must not be
    # affected by the read counter at all.
    for _ in range(3):
        client.get(URL)

    response = client.post("/api/v1/wiki/extract/", {"article_ids": []}, format="json")

    # 400 (validation) rather than 429: it never consulted the read counter.
    assert response.status_code == 400


def test_the_cron_endpoint_stays_exempt(client, settings):
    """PRD section 4: cron is exempt from the demo quota — and from this one."""
    settings.READ_RATE = "1/min"
    client.get(URL)

    # No token, so 403 — but a 429 here would mean the exemption broke.
    response = client.post("/api/v1/ops/cron/daily")

    assert response.status_code == 403
