"""The shape every LLM provider must speak. Contract: ARCHITECTURE section 5.

`chat()` returns a `LLMResult`, not a bare string. Token usage is the only way
`ExtractionRun` can report what a run cost, and a client that returns just
`response.choices[0].message.content` throws it away at the one point where it
is still available.
"""

from typing import Protocol, TypedDict


class LLMResult(TypedDict):
    """One completion plus the accounting that goes with it.

    Token counts are always integers: a provider that omits `usage` yields 0,
    never `None`, so callers can sum them without guarding every access.
    """

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str


class LLMClient(Protocol):
    def chat(self, messages: list[dict], **opts) -> LLMResult: ...
