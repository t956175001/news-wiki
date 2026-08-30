"""Factory tests: one client per process, built from settings, loud when unconfigured.

Building the client is the thing under test here, so these opt out of the
suite-wide guard against constructing a real SDK client. Nothing in this module
calls `chat()`, so nothing reaches the network.
"""

import pytest

from apps.common.exceptions import LLMError
from apps.common.llm.factory import get_llm_client, reset_llm_client
from apps.common.llm.glm import GLMClient

pytestmark = pytest.mark.allow_openai_client


@pytest.fixture(autouse=True)
def _clear_cache():
    # Setup only: by teardown `mock_llm` may have replaced the factory function
    # with a plain lambda, and clearing a cache it does not have would error.
    reset_llm_client()


def test_the_client_is_built_from_settings(settings):
    settings.GLM_API_KEY = "test-key"
    settings.GLM_MODEL = "glm-4.7"
    settings.GLM_BASE_URL = "https://example.invalid/api/paas/v4"

    client = get_llm_client()

    assert isinstance(client, GLMClient)
    assert client.model == "glm-4.7"


def test_the_client_is_cached(settings):
    settings.GLM_API_KEY = "test-key"

    assert get_llm_client() is get_llm_client()


def test_reset_rebuilds_the_client(settings):
    settings.GLM_API_KEY = "test-key"
    first = get_llm_client()

    reset_llm_client()

    assert get_llm_client() is not first


def test_a_missing_api_key_fails_before_any_request(settings):
    settings.GLM_API_KEY = ""

    with pytest.raises(LLMError, match="GLM_API_KEY"):
        get_llm_client()


def test_a_missing_api_key_is_not_cached_as_a_success(settings):
    settings.GLM_API_KEY = ""
    with pytest.raises(LLMError):
        get_llm_client()

    settings.GLM_API_KEY = "test-key"

    assert isinstance(get_llm_client(), GLMClient)


def test_mock_llm_fixture_replaces_the_factory(mock_llm):
    from apps.common.llm import factory

    mock_llm.push_json({"entities": []})

    result = factory.get_llm_client().chat([{"role": "user", "content": "hi"}])

    assert result["content"] == '{"entities": []}'
    assert mock_llm.call_count == 1
