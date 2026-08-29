"""One prompt out, validated JSON back — with retries, accounting, and the
budget guard.

Every LLM call this project makes goes through `invoke_json`: the three
extraction steps and the daily brief all need the same loop (render a prompt,
call the model, parse its JSON, check the shape, retry when any of that fails).
Keeping it here instead of in one app's service layer means the daily spend cap
has a single choke point rather than one per caller.
"""

import json
import logging
import time
from dataclasses import dataclass, field

from tenacity import RetryError, Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from apps.common.budget import check_budget
from apps.common.exceptions import ExtractionStepError, LLMError, SchemaError
from apps.common.prompts.service import render

from .client import LLMClient

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3

# Enough to ride out a transient upstream hiccup without holding a Gunicorn
# thread for a minute; the model rewriting its JSON usually works on attempt two.
_BACKOFF = wait_exponential(multiplier=1, min=1, max=8)

# How much of a malformed response to quote back in the error. Enough to see what
# the model actually did, short enough to not fill the log with one bad reply.
RESPONSE_PREVIEW_CHARS = 1000

_JSON_FENCE_PREFIXES = ("```json", "```JSON", "```")


@dataclass
class StepMeta:
    """One row of `ExtractionRun.step_metrics`. Shape: ARCHITECTURE 3.3."""

    status: str = "done"
    elapsed_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 0
    count: int = 0
    error_message: str = ""
    model: str = ""
    skipped: dict = field(default_factory=dict)

    @classmethod
    def from_metrics(cls, metrics: dict) -> "StepMeta":
        """Rebuild a StepMeta from the dict carried on `ExtractionStepError`.

        `model` is not in the dict, so a failed step's tokens are counted but
        priced at zero. Deliberate: an attempt that never returned a usable
        answer has no model name to price it against.
        """
        return cls(
            status=metrics.get("status", "failed"),
            elapsed_ms=metrics.get("elapsed_ms", 0),
            prompt_tokens=metrics.get("prompt_tokens", 0),
            completion_tokens=metrics.get("completion_tokens", 0),
            attempts=metrics.get("attempts", 0),
            count=metrics.get("count", 0),
            error_message=metrics.get("error_message", ""),
        )

    def merge(self, other: "StepMeta") -> None:
        """Fold another batch's numbers into this step's running total."""
        self.elapsed_ms += other.elapsed_ms
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.attempts += other.attempts
        self.count += other.count
        self.model = other.model or self.model
        for key, value in other.skipped.items():
            self.skipped[key] = self.skipped.get(key, 0) + value
        if other.status == "failed":
            self.status = "failed"
            self.error_message = other.error_message

    def as_dict(self) -> dict:
        data = {
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "count": self.count,
            "attempts": self.attempts,
        }
        if self.status == "failed":
            data["error_message"] = self.error_message
        # Only present when something was actually dropped, so a clean run's
        # metrics stay as documented.
        if any(self.skipped.values()):
            data["skipped"] = {key: value for key, value in self.skipped.items() if value}
        return data


def ms_since(started: float) -> int:
    """Milliseconds elapsed since a `time.monotonic()` reading."""
    return int((time.monotonic() - started) * 1000)


def strip_json_fence(content: str) -> str:
    """Unwrap a ```json fence.

    `response_format={"type": "json_object"}` is supposed to make this
    unnecessary, and the prompts say not to do it, but a fenced reply is a
    perfectly good answer wrapped in three characters — cheaper to unwrap than
    to spend a whole retry on.
    """
    text = content.strip()
    for prefix in _JSON_FENCE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    else:
        return text
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def loads(content: str, prompt_key: str) -> dict:
    """Parse a model reply as JSON, raising `SchemaError` so the caller retries."""
    try:
        return json.loads(strip_json_fence(content))
    except json.JSONDecodeError as exc:
        raise SchemaError(
            f"{prompt_key} did not return JSON ({exc}). Response began: {content[:RESPONSE_PREVIEW_CHARS]!r}"
        ) from exc


def invoke_json(
    prompt_key: str,
    ctx: dict,
    *,
    client: LLMClient,
    run_id: str,
    validate=None,
    trigger: str = "manual",
    sleep=time.sleep,
    **llm_opts,
):
    """Call the model, parse its JSON, and validate — all inside one retry loop.

    Returns `(value, StepMeta)`, where `value` is whatever `validate` returned
    (the extraction steps pass a validator, so they get back `(items, skipped)`)
    or the raw parsed payload when no validator is given.

    Validation runs *inside* the retry rather than after it on purpose. A payload
    that parses but is missing `name` is exactly the kind of mistake a second
    attempt fixes, and leaving it outside would make `SchemaError` from the
    validators a hard failure while the identical error from `json.loads` retries.

    Token counts accumulate across attempts: a retry is a real request that a
    real invoice will list.
    """
    # Before the first request, not after: the point of the cap is to not spend
    # the money. `trigger` decides whether it applies at all (cron is exempt).
    check_budget(trigger)

    meta = StepMeta()
    started = time.monotonic()

    def _attempt():
        meta.attempts += 1
        prompt = render(prompt_key, ctx)
        result = client.chat(
            [{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            run_id=run_id,
            **llm_opts,
        )
        meta.prompt_tokens += result["prompt_tokens"]
        meta.completion_tokens += result["completion_tokens"]
        meta.model = result["model"]

        payload = loads(result["content"], prompt_key)
        return validate(payload) if validate is not None else payload

    # Output quality only. `LLMError` is deliberately absent: the client owns
    # transport and has already spent its own three attempts by the time it
    # raises, so retrying here either repeats a deterministic rejection (a 400
    # from the content filter fails identically every time) or triples the bill
    # on an outage. Measured on 2026-08-29: a step that could not reach the
    # provider took nine upstream calls and ten minutes to give up.
    retrying = Retrying(
        retry=retry_if_exception_type((SchemaError, json.JSONDecodeError)),
        wait=_BACKOFF,
        stop=stop_after_attempt(MAX_ATTEMPTS),
        sleep=sleep,
    )

    def _failed(cause: BaseException) -> ExtractionStepError:
        meta.status = "failed"
        meta.error_message = str(cause)
        meta.elapsed_ms = ms_since(started)
        logger.error(
            "run_id=%s step %s failed after %s attempt(s): %s", run_id, prompt_key, meta.attempts, cause
        )
        return ExtractionStepError(prompt_key, meta.as_dict(), cause)

    try:
        value = retrying(_attempt)
    except RetryError as exc:
        raise _failed(exc.last_attempt.exception()) from exc.last_attempt.exception()
    except LLMError as exc:
        # Not retried above, but still has to be reported as a failed step: an
        # LLMError escaping raw would skip the metrics and leave the run stuck
        # on "running" forever.
        raise _failed(exc) from exc

    meta.elapsed_ms = ms_since(started)
    return value, meta
