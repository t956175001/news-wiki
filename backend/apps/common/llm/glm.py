"""Zhipu GLM client, spoken to through the OpenAI-compatible SDK.

Retries live here rather than in the SDK: `max_retries=0` is set on the
underlying client so there is exactly one retry policy, and it is the one whose
attempt count lands in `ExtractionRun.step_metrics`. Two nested policies would
turn 3 attempts into 9 and make the recorded numbers a lie.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from openai import APIConnectionError, APIStatusError, OpenAI, OpenAIError
from tenacity import RetryError, Retrying, stop_after_attempt, wait_exponential

from apps.common.exceptions import ContentFilteredError, LLMError

from .client import LLMResult
from .ratelimit import TokenBucket, get_bucket

logger = logging.getLogger(__name__)

# Reasoning models spend most of a call thinking before the first token appears,
# and GLM-5.3-Flash cannot be asked to stop (`thinking.type` only accepts
# "enabled"). 120s was not enough for a three-article corpus; overridable via
# `LLM_TIMEOUT_SECONDS` because the right value follows the model choice.
DEFAULT_TIMEOUT = 300.0
MAX_ATTEMPTS = 3

# Everything this project asks the model for is structured extraction, where
# sampling variety is a liability rather than a feature.
DEFAULT_TEMPERATURE = 0.2

# 408 Request Timeout, 409 Conflict and 429 Too Many Requests are transient; so
# is anything 5xx. The rest (401 bad key, 400 malformed request, 404 unknown
# model) will fail identically on every attempt, so retrying only delays the
# error and burns quota.
RETRYABLE_STATUSES = frozenset({408, 409, 429})

# GLM answers a safety refusal with HTTP 400 and this code in the body. It is a
# policy decision rather than a fault: the same prompt is refused every time, so
# callers need to tell it apart from an outage and stop instead of retrying.
CONTENT_FILTER_CODE = "1301"

_BACKOFF = wait_exponential(multiplier=1, min=1, max=20)

# A provider is free to send `Retry-After: 3600`. Honouring that would park a
# Gunicorn thread for an hour, so cap it and let the attempt budget run out.
MAX_RETRY_AFTER = 60.0


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, APIConnectionError):  # covers APITimeoutError
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in RETRYABLE_STATUSES or exc.status_code >= 500
    return False


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Seconds requested by a `Retry-After` header, if the server sent a usable one."""
    if not isinstance(exc, APIStatusError):
        return None

    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None

    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None

    try:
        seconds = float(str(raw).strip())
    except ValueError:
        # The HTTP-date form is legal but GLM does not use it; backing off
        # exponentially is a fine answer.
        return None

    if seconds < 0:
        return None
    return min(seconds, MAX_RETRY_AFTER)


def _failure(retry_state) -> BaseException | None:
    outcome = retry_state.outcome
    return outcome.exception() if outcome is not None and outcome.failed else None


def _should_retry(retry_state) -> bool:
    exc = _failure(retry_state)
    return exc is not None and _is_retryable(exc)


def _wait(retry_state) -> float:
    """Server-directed wait when there is one, exponential backoff otherwise."""
    exc = _failure(retry_state)
    retry_after = _retry_after_seconds(exc) if exc is not None else None
    if retry_after is not None:
        return retry_after
    return _BACKOFF(retry_state)


def _is_content_filtered(exc: APIStatusError) -> bool:
    """Whether a 400 is the safety filter rather than a malformed request."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        if body.get("contentFilter"):
            return True
        error = body.get("error")
        return isinstance(error, dict) and str(error.get("code")) == CONTENT_FILTER_CODE
    # The SDK does not always hand back a parsed body; the message still quotes it.
    text = str(exc)
    return "contentFilter" in text or f"'{CONTENT_FILTER_CODE}'" in text


@dataclass(frozen=True)
class _Message:
    content: str


@dataclass(frozen=True)
class _Choice:
    message: _Message


@dataclass(frozen=True)
class _Completion:
    """A consumed stream folded back into the non-streaming response shape.

    Streaming exists here to keep the connection busy, not to show tokens as they
    arrive — nothing downstream wants a partial answer. Rebuilding the whole
    response means `_to_result` and every caller stay unaware of the difference.
    """

    choices: list
    usage: object | None
    model: str | None


def _collapse_stream(chunks) -> _Completion:
    """Drain a streamed completion into a single response.

    Only `delta.content` is collected. Reasoning models also stream
    `delta.reasoning_content`, which is the model thinking out loud on the way to
    the answer — interesting, and not what was asked for.
    """
    parts: list[str] = []
    usage = None
    model = None

    for chunk in chunks:
        model = getattr(chunk, "model", None) or model
        # Usage rides on the final chunk, which carries no choices.
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
        for choice in getattr(chunk, "choices", None) or []:
            piece = getattr(getattr(choice, "delta", None), "content", None)
            if piece:
                parts.append(piece)

    return _Completion(choices=[_Choice(_Message("".join(parts)))], usage=usage, model=model)


def _usage_value(usage: object, name: str) -> int:
    """Read one usage counter, tolerating objects, dicts and absence alike."""
    if usage is None:
        return 0
    value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


class GLMClient:
    """`LLMClient` implementation for GLM's OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_attempts: int = MAX_ATTEMPTS,
        stream: bool = True,
        bucket: TokenBucket | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model = model
        self.max_attempts = max_attempts
        self._stream = stream
        self._bucket = bucket if bucket is not None else get_bucket()
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
        self._sleep = sleep

    def chat(self, messages: list[dict], **opts) -> LLMResult:
        """Send *messages* and return the completion with its token usage.

        `run_id` is accepted as an option purely for logging — every LLM log line
        has to carry it so a run can be traced end to end.
        """
        run_id = str(opts.pop("run_id", "-"))
        model = str(opts.pop("model", None) or self.model)
        params = {"temperature": DEFAULT_TEMPERATURE, **opts}
        if self._stream:
            # A reasoning model can think for two minutes before emitting a
            # token, and an idle connection that long gets dropped in between.
            # Streaming keeps bytes moving; nothing here shows partial output.
            params.setdefault("stream", True)
            # Without this the final chunk carries no usage and every run would
            # report zero tokens and zero cost.
            params.setdefault("stream_options", {"include_usage": True})

        attempts = 0

        def _attempt():
            nonlocal attempts
            attempts += 1
            # Retries are real requests, so they pay for a token too.
            self._bucket.acquire()
            response = self._client.chat.completions.create(model=model, messages=messages, **params)
            # Drained inside the retry, so a connection dropped mid-stream is
            # just another failed attempt rather than a half-read answer.
            return _collapse_stream(response) if params.get("stream") else response

        started = time.monotonic()
        try:
            response = self._retrying()(_attempt)
        except RetryError as exc:
            last = exc.last_attempt.exception()
            logger.error(
                "run_id=%s LLM call to %s failed after %s attempts: %s",
                run_id,
                model,
                attempts,
                last,
            )
            raise LLMError(f"LLM call failed after {attempts} attempts: {last}") from last
        except APIStatusError as exc:
            # Not retryable — a bad key, a malformed request, or a refusal.
            if _is_content_filtered(exc):
                logger.error("run_id=%s LLM call to %s refused by the content filter", run_id, model)
                raise ContentFilteredError(f"LLM refused to answer on safety grounds: {exc}") from exc
            logger.error(
                "run_id=%s LLM call to %s rejected (HTTP %s): %s", run_id, model, exc.status_code, exc
            )
            raise LLMError(f"LLM call rejected with HTTP {exc.status_code}: {exc}") from exc
        except OpenAIError as exc:
            # Provider exceptions must not escape this module; everything above
            # only knows about AppError subclasses.
            logger.error("run_id=%s LLM call to %s failed: %s", run_id, model, exc)
            raise LLMError(f"LLM call failed: {exc}") from exc

        result = self._to_result(response, model, run_id)
        logger.info(
            "run_id=%s LLM %s ok in %sms after %s attempt(s): %s prompt + %s completion tokens",
            run_id,
            result["model"],
            int((time.monotonic() - started) * 1000),
            attempts,
            result["prompt_tokens"],
            result["completion_tokens"],
        )
        return result

    def _retrying(self) -> Retrying:
        # Built per call so an injected `sleep` stays test-visible and no retry
        # state leaks between calls.
        return Retrying(
            retry=_should_retry,
            wait=_wait,
            stop=stop_after_attempt(self.max_attempts),
            sleep=self._sleep,
        )

    def _to_result(self, response: object, requested_model: str, run_id: str) -> LLMResult:
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMError("LLM returned no choices")

        content = getattr(getattr(choices[0], "message", None), "content", None)
        if not content:
            raise LLMError("LLM returned an empty completion")

        usage = getattr(response, "usage", None)
        if usage is None:
            # Not fatal, but it silently zeroes the run's cost report, so say so.
            logger.warning("run_id=%s LLM response carried no usage block; recording 0 tokens", run_id)

        prompt_tokens = _usage_value(usage, "prompt_tokens")
        completion_tokens = _usage_value(usage, "completion_tokens")
        total_tokens = _usage_value(usage, "total_tokens") or prompt_tokens + completion_tokens

        return LLMResult(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=str(getattr(response, "model", None) or requested_model),
        )
