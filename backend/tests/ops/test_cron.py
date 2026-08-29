"""The cron endpoint: the one door into this API that spends money on request.

It is protected by a shared secret and nothing else, so the tests that matter are
the ones about who gets turned away.
"""

import pytest
from rest_framework.test import APIClient

from apps.ops.models import ExtractionRun
from apps.ops.views import CRON_TOKEN_HEADER

pytestmark = pytest.mark.django_db

URL = "/api/v1/ops/cron/daily"
TOKEN = "cron-token-for-tests"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def token(settings):
    settings.CRON_TOKEN = TOKEN
    return TOKEN


@pytest.fixture(autouse=True)
def no_background(monkeypatch):
    """Record the dispatch instead of running the pipeline on a real thread."""
    started = []

    def _record(label, func, *args, **kwargs):
        started.append({"label": label, "func": func, "args": args, "kwargs": kwargs})

    monkeypatch.setattr("apps.ops.views.run_in_background", _record)
    return started


def test_a_request_without_a_token_is_refused(client):
    response = client.post(URL)

    assert response.status_code == 403
    assert response.json() == {"code": "FORBIDDEN", "detail": "无效的 cron token。"}


def test_a_request_with_the_wrong_token_is_refused(client):
    response = client.post(URL, headers={CRON_TOKEN_HEADER: "not-the-token"})

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_a_refused_request_starts_nothing(client, no_background):
    client.post(URL, headers={CRON_TOKEN_HEADER: "not-the-token"})

    assert no_background == []
    assert not ExtractionRun.objects.exists()


def test_an_unset_cron_token_refuses_everyone(client, settings):
    settings.CRON_TOKEN = ""

    assert client.post(URL).status_code == 403
    assert client.post(URL, headers={CRON_TOKEN_HEADER: ""}).status_code == 403


def test_the_right_token_gets_a_run_id_back(client):
    response = client.post(URL, headers={CRON_TOKEN_HEADER: TOKEN})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    assert len(body["run_id"]) == 32
    int(body["run_id"], 16)  # a uuid4 hex, not a stringified pk


def test_the_run_exists_before_the_response_is_sent(client):
    response = client.post(URL, headers={CRON_TOKEN_HEADER: TOKEN})

    run = ExtractionRun.objects.get(run_id=response.json()["run_id"])
    assert run.status == "running"
    assert run.trigger == "cron"
    # The frontend polls on this id, so the prompt snapshot has to be there too.
    assert run.prompt_versions != {}


def test_the_pipeline_is_handed_the_run_it_returned(client, no_background):
    response = client.post(URL, headers={CRON_TOKEN_HEADER: TOKEN})

    dispatched = no_background[0]
    assert dispatched["kwargs"]["run"].run_id == response.json()["run_id"]
    assert dispatched["kwargs"]["trigger"] == "cron"


def test_cron_is_exempt_from_the_demo_write_quota(client, settings):
    settings.DEMO_MODE = True
    settings.DEMO_WRITE_RATE = "3/day"

    codes = [client.post(URL, headers={CRON_TOKEN_HEADER: TOKEN}).status_code for _ in range(5)]

    assert codes == [202] * 5


def test_get_is_not_allowed(client):
    assert client.get(URL, headers={CRON_TOKEN_HEADER: TOKEN}).status_code == 405
