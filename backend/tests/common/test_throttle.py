"""The per-IP demo quota, exercised through the endpoint that carries it.

Tested end to end rather than against the throttle class alone, because the part
worth protecting is the whole chain: DRF raises `Throttled`, the exception
handler turns it into the project's error envelope, and the frontend shows the
Chinese sentence in a banner rather than a stack trace.
"""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.drf_exceptions import DEMO_THROTTLED_DETAIL
from apps.ingest.models import RawArticle
from apps.ops.models import ExtractionRun

pytestmark = pytest.mark.django_db

URL = "/api/v1/wiki/extract/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def demo_mode(settings):
    settings.DEMO_MODE = True
    settings.DEMO_WRITE_RATE = "3/day"
    settings.LLM_DAILY_BUDGET_CNY = 5.0


@pytest.fixture(autouse=True)
def no_background(monkeypatch):
    """The quota is what is under test; the extraction itself is not."""
    started = []
    monkeypatch.setattr(
        "apps.wiki.views.run_in_background",
        lambda label, func, *args, **kwargs: started.append(label),
    )
    return started


@pytest.fixture
def article():
    return RawArticle.objects.create(
        title="测试文章",
        url="https://example.com/news/throttle",
        content="OpenAI 于本周正式发布 GPT-5。",
        content_hash="throttle-hash-0001",
        publish_time=timezone.now(),
    )


def extract(client, article, **kwargs):
    return client.post(URL, {"article_ids": [article.pk]}, format="json", **kwargs)


def test_the_fourth_request_of_the_day_is_refused(client, article):
    codes = [extract(client, article).status_code for _ in range(4)]

    assert codes == [202, 202, 202, 429]


def test_the_refusal_is_the_documented_chinese_message(client, article):
    for _ in range(3):
        extract(client, article)

    response = extract(client, article)

    assert response.json() == {"code": "RATE_LIMITED", "detail": DEMO_THROTTLED_DETAIL}
    assert DEMO_THROTTLED_DETAIL == "演示模式下每个 IP 每天可触发 3 次实时抽取，明天再来试试～"


def test_a_refused_request_starts_no_run(client, article, no_background):
    for _ in range(4):
        extract(client, article)

    assert len(no_background) == 3
    assert ExtractionRun.objects.count() == 3


def test_the_quota_is_per_ip(client, article):
    for _ in range(3):
        extract(client, article)

    other_visitor = extract(client, article, REMOTE_ADDR="10.0.0.99")

    assert other_visitor.status_code == 202


def test_the_rate_is_configurable(client, article, settings):
    settings.DEMO_WRITE_RATE = "1/day"

    codes = [extract(client, article).status_code for _ in range(2)]

    assert codes == [202, 429]


def test_a_self_hosted_instance_is_not_throttled(client, article, settings):
    settings.DEMO_MODE = False

    codes = [extract(client, article).status_code for _ in range(6)]

    assert codes == [202] * 6


# --- the other guard rail on the same endpoint --------------------------


def test_an_exhausted_budget_returns_a_read_only_response(client, article, settings):
    settings.LLM_DAILY_BUDGET_CNY = 0.0

    response = extract(client, article)

    assert response.status_code == 503
    assert response.json()["code"] == "BUDGET_EXCEEDED"
    assert not ExtractionRun.objects.exists()


def test_unknown_article_ids_are_rejected(client, article):
    response = client.post(URL, {"article_ids": [article.pk + 999]}, format="json")

    assert response.status_code == 404
    assert response.json()["code"] == "NO_ARTICLES"


def test_an_empty_body_is_a_validation_error(client):
    response = client.post(URL, {"article_ids": []}, format="json")

    assert response.status_code == 400
    assert "article_ids" in response.json()["fields"]
