"""Domain exceptions.

Every business failure raises one of these instead of a bare `Exception`, so
`drf_exceptions.custom_exception_handler` can turn it into a stable
`{"code": ..., "detail": ...}` response. Subclasses only declare a code; the
HTTP status mapping lives in `drf_exceptions`.
"""


class AppError(Exception):
    """Base class for every domain error raised by this project."""

    default_code = "APP_ERROR"

    def __init__(self, detail: str, code: str | None = None, fields: dict | None = None):
        self.detail = detail
        self.code = code or self.default_code
        self.fields = fields
        super().__init__(detail)


class FetchError(AppError):
    """RSS feed or article page could not be retrieved."""

    default_code = "FETCH_ERROR"


class LLMError(AppError):
    """The LLM call failed, or its output could not be used."""

    default_code = "LLM_ERROR"


class ParseError(AppError):
    """Input could not be parsed into the expected shape."""

    default_code = "PARSE_ERROR"


class ExtractionStepError(AppError):
    """One step of the extraction pipeline exhausted its retries.

    Carries the step name and that step's metrics so the orchestrator can write
    them straight into `ExtractionRun.step_metrics` without re-deriving them.
    """

    default_code = "EXTRACTION_STEP_FAILED"

    def __init__(self, step: str, metrics: dict, cause: BaseException):
        self.step = step
        self.metrics = metrics
        self.cause = cause
        super().__init__(f"Step {step} failed after {metrics.get('attempts', 0)} attempt(s): {cause}")


class PromptRenderError(AppError):
    """A prompt template is missing, has no active version, or lacks variables."""

    default_code = "PROMPT_RENDER_ERROR"


class RateLimitedError(AppError):
    """A guard rail rejected the request because it came in too fast."""

    default_code = "RATE_LIMITED"


class BudgetExceededError(AppError):
    """The daily LLM spend cap tripped; no further calls this day."""

    default_code = "BUDGET_EXCEEDED"
