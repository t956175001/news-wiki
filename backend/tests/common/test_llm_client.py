"""GLMClient tests. The OpenAI SDK class is replaced wholesale — nothing dials out.

The point of these is the contract in ARCHITECTURE section 5: a `LLMResult` with
real token counts, retries that are counted and bounded, and provider exceptions
that never escape as themselves.
"""

from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, OpenAIError

from apps.common.exceptions import ContentFilteredError, LLMError
from apps.common.llm import glm
from apps.common.llm.glm import GLMClient
from apps.common.llm.ratelimit import TokenBucket

BASE_URL = "https://example.invalid/api/paas/v4"


def _response(content="{}", *, prompt=10, completion=5, total=None, model="glm-4.7", with_usage=True):
    usage = None
    if with_usage:
        usage = SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion if total is None else total,
        )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=usage,
        model=model,
    )


def _request():
    return httpx.Request("POST", f"{BASE_URL}/chat/completions")


def _status_error(status_code: int, headers: dict | None = None):
    response = httpx.Response(status_code, headers=headers or {}, request=_request())
    return APIStatusError("upstream said no", response=response, body=None)


class _Harness:
    """Holds the fake SDK client plus the sleeps the retry policy asked for."""

    def __init__(self):
        self.script: list = []
        self.calls: list[dict] = []
        self.init_kwargs: dict = {}
        self.slept: list[float] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("fake SDK called more times than the test scripted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def harness(monkeypatch):
    h = _Harness()

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            h.init_kwargs = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=h.create))

    monkeypatch.setattr(glm, "OpenAI", _FakeOpenAI)
    return h


@pytest.fixture
def build(harness):
    def _build(script, **kwargs):
        harness.script = list(script)
        # Rate limiting is exercised in test_ratelimit.py; an unthrottled bucket
        # keeps these tests from sleeping for real.
        kwargs.setdefault("bucket", TokenBucket(0))
        # Most of these pin the plain request/response contract; the streaming
        # path has its own section at the bottom.
        kwargs.setdefault("stream", False)
        return GLMClient(
            api_key="test-key",
            model="glm-4.7",
            base_url=BASE_URL,
            sleep=harness.slept.append,
            **kwargs,
        )

    return _build


def test_chat_returns_content_and_usage(build, harness):
    client = build([_response('{"entities": []}', prompt=1234, completion=56)])

    result = client.chat([{"role": "user", "content": "hi"}])

    assert result == {
        "content": '{"entities": []}',
        "prompt_tokens": 1234,
        "completion_tokens": 56,
        "total_tokens": 1290,
        "model": "glm-4.7",
    }
    assert harness.calls[0]["model"] == "glm-4.7"


def test_chat_fills_zero_when_usage_is_missing(build):
    # The regression this whole contract exists for: no usage must mean 0, not
    # None, or every sum downstream blows up.
    client = build([_response("ok", with_usage=False)])

    result = client.chat([{"role": "user", "content": "hi"}])

    assert result["prompt_tokens"] == 0
    assert result["completion_tokens"] == 0
    assert result["total_tokens"] == 0
    assert isinstance(result["total_tokens"], int)


def test_chat_fills_zero_when_usage_fields_are_null(build):
    client = build(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=None, completion_tokens=None, total_tokens=None),
                model="glm-4.7",
            )
        ]
    )

    result = client.chat([{"role": "user", "content": "hi"}])

    assert (result["prompt_tokens"], result["completion_tokens"], result["total_tokens"]) == (0, 0, 0)


def test_chat_derives_total_when_the_provider_omits_it(build):
    client = build([_response("ok", prompt=30, completion=12, total=0)])

    assert client.chat([{"role": "user", "content": "hi"}])["total_tokens"] == 42


def test_chat_accepts_a_usage_dict(build):
    client = build(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                model="glm-4.7",
            )
        ]
    )

    assert client.chat([{"role": "user", "content": "hi"}])["prompt_tokens"] == 7


def test_chat_passes_options_through_and_defaults_temperature(build, harness):
    client = build([_response()])

    client.chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
        run_id="abc123",
    )

    call = harness.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["temperature"] == glm.DEFAULT_TEMPERATURE
    # run_id is for logging only and must never reach the provider.
    assert "run_id" not in call


def test_chat_honours_a_per_call_model_override(build, harness):
    client = build([_response(model="glm-4.6")])

    result = client.chat([{"role": "user", "content": "hi"}], model="glm-4.6")

    assert harness.calls[0]["model"] == "glm-4.6"
    assert result["model"] == "glm-4.6"


def test_sdk_retries_are_disabled_so_the_attempt_count_stays_honest(build, harness):
    build([_response()])

    assert harness.init_kwargs["max_retries"] == 0
    assert harness.init_kwargs["base_url"] == BASE_URL


def test_chat_retries_after_a_429_and_succeeds(build, harness):
    client = build([_status_error(429), _response("recovered")])

    result = client.chat([{"role": "user", "content": "hi"}])

    assert result["content"] == "recovered"
    assert len(harness.calls) == 2


def test_chat_waits_for_the_retry_after_header(build, harness):
    client = build([_status_error(429, {"retry-after": "7"}), _response()])

    client.chat([{"role": "user", "content": "hi"}])

    assert harness.slept == [7.0]


def test_retry_after_is_capped_so_a_worker_cannot_be_parked(build, harness):
    client = build([_status_error(429, {"retry-after": "3600"}), _response()])

    client.chat([{"role": "user", "content": "hi"}])

    assert harness.slept == [glm.MAX_RETRY_AFTER]


def test_a_malformed_retry_after_falls_back_to_backoff(build, harness):
    client = build([_status_error(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}), _response()])

    client.chat([{"role": "user", "content": "hi"}])

    assert harness.slept and harness.slept[0] > 0


def test_chat_retries_connection_errors(build, harness):
    client = build([APIConnectionError(request=_request()), _response("recovered")])

    assert client.chat([{"role": "user", "content": "hi"}])["content"] == "recovered"
    assert len(harness.calls) == 2


def test_chat_retries_server_errors(build, harness):
    client = build([_status_error(503), _response("recovered")])

    assert client.chat([{"role": "user", "content": "hi"}])["content"] == "recovered"
    assert len(harness.calls) == 2


def test_chat_raises_llm_error_once_attempts_run_out(build, harness):
    client = build([_status_error(429), _status_error(429), _status_error(429)])

    with pytest.raises(LLMError) as exc:
        client.chat([{"role": "user", "content": "hi"}])

    assert exc.value.code == "LLM_ERROR"
    assert "3 attempts" in exc.value.detail
    assert len(harness.calls) == glm.MAX_ATTEMPTS


def test_chat_does_not_retry_an_unauthorized_key(build, harness):
    client = build([_status_error(401)])

    with pytest.raises(LLMError) as exc:
        client.chat([{"role": "user", "content": "hi"}])

    # Retrying a bad key three times only delays the same error.
    assert len(harness.calls) == 1
    assert "401" in exc.value.detail


def test_chat_does_not_retry_a_malformed_request(build, harness):
    client = build([_status_error(400)])

    with pytest.raises(LLMError):
        client.chat([{"role": "user", "content": "hi"}])

    assert len(harness.calls) == 1


def test_a_negative_retry_after_falls_back_to_backoff(build, harness):
    client = build([_status_error(429, {"retry-after": "-5"}), _response()])

    client.chat([{"role": "user", "content": "hi"}])

    # Honouring it literally would mean not waiting at all, which is how a 429
    # turns into three 429s.
    assert harness.slept and harness.slept[0] > 0


def test_a_429_with_no_headers_at_all_still_backs_off(build, harness):
    headerless = _status_error(429)
    # A gateway can reject a request before the SDK has a parsed response to
    # read a header off. The backoff still has to happen.
    headerless.response = SimpleNamespace(status_code=429)
    client = build([headerless, _response()])

    client.chat([{"role": "user", "content": "hi"}])

    assert harness.slept and harness.slept[0] > 0


def test_an_sdk_error_that_is_neither_transport_nor_status_is_not_retried(build, harness):
    client = build([OpenAIError("the SDK could not build the request")])

    with pytest.raises(LLMError) as exc:
        client.chat([{"role": "user", "content": "hi"}])

    # No status code means no way to tell whether a retry could help, and the
    # provider's exception types must not escape this module either way.
    assert len(harness.calls) == 1
    assert "could not build the request" in exc.value.detail


def test_chat_rejects_an_empty_completion(build):
    client = build([_response(content="")])

    with pytest.raises(LLMError, match="empty completion"):
        client.chat([{"role": "user", "content": "hi"}])


def test_chat_rejects_a_response_with_no_choices(build):
    client = build([SimpleNamespace(choices=[], usage=None, model="glm-4.7")])

    with pytest.raises(LLMError, match="no choices"):
        client.chat([{"role": "user", "content": "hi"}])


def test_every_attempt_pays_the_rate_limiter(build, harness):
    bucket = TokenBucket(60, sleep=lambda _: None)
    client = build([_status_error(429), _response()], bucket=bucket)

    client.chat([{"role": "user", "content": "hi"}])

    assert bucket._tokens == pytest.approx(58.0, abs=0.01)


# --- content filter -----------------------------------------------------


def _filtered_error(body=None):
    """The 400 GLM returns when its safety filter blocks the answer."""
    response = httpx.Response(400, request=_request())
    if body is None:
        body = {
            "contentFilter": [{"level": 1, "role": "assistant"}],
            "error": {"code": "1301", "message": "系统检测到输入或生成内容可能包含不安全或敏感内容"},
        }
    return APIStatusError("content filtered", response=response, body=body)


def test_a_safety_refusal_is_not_an_ordinary_llm_error(build, harness):
    """It has to be distinguishable: callers decide whether they can carry on."""
    client = build([_filtered_error()])

    with pytest.raises(ContentFilteredError):
        client.chat([{"role": "user", "content": "hi"}])

    assert len(harness.calls) == 1


def test_a_safety_refusal_is_recognised_from_the_error_code_alone(build):
    client = build([_filtered_error({"error": {"code": "1301", "message": "不安全"}})])

    with pytest.raises(ContentFilteredError):
        client.chat([{"role": "user", "content": "hi"}])


def test_a_safety_refusal_is_recognised_when_the_body_was_not_parsed(build):
    # The SDK hands back `body=None` often enough that reading only the parsed
    # body would let a refusal through as a generic 400.
    response = httpx.Response(400, request=_request())
    error = APIStatusError(
        "Error code: 400 - {'contentFilter': [{'level': 1}]}", response=response, body=None
    )
    client = build([error])

    with pytest.raises(ContentFilteredError):
        client.chat([{"role": "user", "content": "hi"}])


def test_an_ordinary_bad_request_is_still_a_plain_llm_error(build):
    client = build([_status_error(400)])

    with pytest.raises(LLMError) as excinfo:
        client.chat([{"role": "user", "content": "hi"}])

    assert not isinstance(excinfo.value, ContentFilteredError)


# --- streaming ----------------------------------------------------------


def _chunk(content=None, *, usage=None, model="glm-5.3-flash", reasoning=None):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    choices = [] if content is None and reasoning is None else [SimpleNamespace(delta=delta)]
    return SimpleNamespace(choices=choices, usage=usage, model=model)


def _stream(*chunks):
    return iter(chunks)


def test_a_streamed_reply_is_reassembled(build, harness):
    client = build(
        [
            _stream(
                _chunk('{"entities"'),
                _chunk(": []}"),
                _chunk(usage=SimpleNamespace(prompt_tokens=2725, completion_tokens=4666, total_tokens=7391)),
            )
        ],
        stream=True,
    )

    result = client.chat([{"role": "user", "content": "hi"}])

    assert result["content"] == '{"entities": []}'
    assert result["prompt_tokens"] == 2725
    assert result["completion_tokens"] == 4666
    assert result["model"] == "glm-5.3-flash"


def test_streaming_asks_for_usage(build, harness):
    """Without `include_usage` every streamed run would report zero cost."""
    client = build([_stream(_chunk("{}"), _chunk(usage=None))], stream=True)

    client.chat([{"role": "user", "content": "hi"}])

    assert harness.calls[0]["stream"] is True
    assert harness.calls[0]["stream_options"] == {"include_usage": True}


def test_streamed_reasoning_is_not_part_of_the_answer(build):
    """A reasoning model streams its thinking too; only the answer is wanted."""
    client = build(
        [_stream(_chunk(reasoning="先想一想……"), _chunk('{"ok": true}'), _chunk(reasoning="再想想"))],
        stream=True,
    )

    result = client.chat([{"role": "user", "content": "hi"}])

    assert result["content"] == '{"ok": true}'


def test_a_stream_that_carries_no_answer_is_an_empty_completion(build):
    client = build([_stream(_chunk(reasoning="只有思考，没有答案"))], stream=True)

    with pytest.raises(LLMError, match="empty completion"):
        client.chat([{"role": "user", "content": "hi"}])


def test_a_connection_dropped_mid_stream_is_retried(build, harness):
    def _broken():
        yield _chunk('{"partial"')
        raise APIConnectionError(request=_request())

    client = build(
        [_broken(), _stream(_chunk("{}"), _chunk(usage=None))],
        stream=True,
    )

    result = client.chat([{"role": "user", "content": "hi"}])

    # The half-read answer is discarded rather than returned as content.
    assert result["content"] == "{}"
    assert len(harness.calls) == 2


def test_not_streaming_sends_no_stream_flag(build, harness):
    client = build([_response()], stream=False)

    client.chat([{"role": "user", "content": "hi"}])

    assert "stream" not in harness.calls[0]
