"""Single construction point for the LLM client.

Services call `get_llm_client()` and depend on the `LLMClient` protocol, so
swapping the provider is a change in this file only. The instance is cached
because the underlying SDK client owns an HTTP connection pool that is worth
keeping warm across a run.
"""

import logging
from functools import lru_cache

from django.conf import settings

from apps.common.exceptions import LLMError

from .client import LLMClient
from .glm import GLMClient

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """The process-wide GLM client, built from settings.

    Raises `LLMError` when `GLM_API_KEY` is unset. Failing here — loudly, at the
    first call — beats letting the provider return a 401 three retries later.
    """
    if not settings.GLM_API_KEY:
        raise LLMError("GLM_API_KEY is not configured; set it in .env before running extraction")

    logger.debug("Building GLM client for model %s at %s", settings.GLM_MODEL, settings.GLM_BASE_URL)
    return GLMClient(
        api_key=settings.GLM_API_KEY,
        model=settings.GLM_MODEL,
        base_url=settings.GLM_BASE_URL,
    )


def reset_llm_client() -> None:
    """Drop the cached client. For tests and for settings changes at runtime."""
    get_llm_client.cache_clear()
