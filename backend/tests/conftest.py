"""Fixtures shared by the whole suite.

House rule (CLAUDE.md): no test ever makes a real LLM call. `mock_llm` is the
one seam every LLM-touching test goes through, so there is a single place to
look when the client contract changes.
"""

import json
from collections import deque

import pytest

from apps.common.llm import factory
from apps.common.llm.client import LLMResult
from apps.common.llm.ratelimit import reset_bucket


class FakeLLMClient:
    """Scripted stand-in for `LLMClient`.

    Queue what the model should say with `push()` / `push_json()` / `push_error()`,
    then assert against `calls` afterwards. Running out of scripted responses is
    an error rather than a default reply: a pipeline that calls the model more
    times than the test expects is exactly the bug worth catching.
    """

    def __init__(self, model: str = "glm-4.7"):
        self.model = model
        self.calls: list[dict] = []
        self._queue: deque = deque()

    # --- scripting ---

    def push(
        self,
        content: str,
        *,
        prompt_tokens: int = 100,
        completion_tokens: int = 20,
        model: str | None = None,
    ) -> "FakeLLMClient":
        self._queue.append(
            LLMResult(
                content=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                model=model or self.model,
            )
        )
        return self

    def push_json(self, payload, **kwargs) -> "FakeLLMClient":
        return self.push(json.dumps(payload, ensure_ascii=False), **kwargs)

    def push_error(self, exc: BaseException) -> "FakeLLMClient":
        self._queue.append(exc)
        return self

    # --- LLMClient protocol ---

    def chat(self, messages: list[dict], **opts) -> LLMResult:
        self.calls.append({"messages": messages, "opts": opts})
        if not self._queue:
            raise AssertionError(
                f"FakeLLMClient was called {len(self.calls)} time(s) but only "
                f"{len(self.calls) - 1} response(s) were queued"
            )
        item = self._queue.popleft()
        if isinstance(item, BaseException):
            raise item
        return item

    # --- assertions helpers ---

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def prompt_at(self, index: int) -> str:
        """The user message sent on call *index*."""
        return self.calls[index]["messages"][-1]["content"]


@pytest.fixture
def mock_llm(monkeypatch):
    """A `FakeLLMClient` that `get_llm_client()` also hands out.

    Services take an optional client argument, so most tests can just pass the
    fixture straight in; the factory patch covers the paths that resolve the
    client themselves.
    """
    fake = FakeLLMClient()

    # Held by reference: after the patch, `factory.get_llm_client` is a plain
    # lambda with no `cache_clear` to call on the way out.
    real_get_client = factory.get_llm_client
    real_get_client.cache_clear()

    monkeypatch.setattr(factory, "get_llm_client", lambda: fake)
    monkeypatch.setattr("apps.common.llm.get_llm_client", lambda: fake)

    yield fake

    real_get_client.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_rate_limit_bucket():
    """Stop one test's spent tokens from making the next one sleep."""
    reset_bucket()
    yield
    reset_bucket()
