"""LLM access layer. Contract: `docs/ARCHITECTURE.md` section 5.

Callers should depend on `LLMClient` / `LLMResult` and obtain instances through
`get_llm_client()`, never by constructing a provider class directly.
"""

from .client import LLMClient, LLMResult
from .factory import get_llm_client, reset_llm_client

__all__ = ["LLMClient", "LLMResult", "get_llm_client", "reset_llm_client"]
