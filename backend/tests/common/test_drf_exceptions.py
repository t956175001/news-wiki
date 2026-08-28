"""The error envelope every endpoint is contractually required to produce."""

import pytest
from rest_framework.exceptions import NotFound, Throttled, ValidationError

from apps.common.drf_exceptions import DEMO_THROTTLED_DETAIL, custom_exception_handler
from apps.common.exceptions import AppError, BudgetExceededError, FetchError, LLMError


def handle(exc):
    return custom_exception_handler(exc, {})


@pytest.mark.parametrize(
    ("exc", "expected_code", "expected_status"),
    [
        (AppError("boom"), "APP_ERROR", 500),
        (FetchError("feed down"), "FETCH_ERROR", 502),
        (LLMError("bad json"), "LLM_ERROR", 502),
        (BudgetExceededError("cap hit"), "BUDGET_EXCEEDED", 503),
    ],
)
def test_domain_errors_map_to_codes_and_statuses(exc, expected_code, expected_status):
    response = handle(exc)

    assert response.status_code == expected_status
    assert response.data == {"code": expected_code, "detail": str(exc)}


def test_domain_error_can_carry_field_details():
    response = handle(AppError("invalid", fields={"url": ["required"]}))

    assert response.data["fields"] == {"url": ["required"]}


def test_throttled_gets_the_demo_mode_message():
    response = handle(Throttled(wait=60))

    assert response.status_code == 429
    assert response.data == {"code": "RATE_LIMITED", "detail": DEMO_THROTTLED_DETAIL}


def test_drf_errors_keep_the_same_envelope():
    response = handle(NotFound("nothing here"))

    assert response.status_code == 404
    assert response.data["code"] == "not_found"
    assert response.data["detail"] == "nothing here"


def test_validation_errors_expose_per_field_messages():
    response = handle(ValidationError({"name": ["This field is required."]}))

    assert response.status_code == 400
    assert response.data["fields"] == {"name": ["This field is required."]}


def test_non_api_exceptions_are_not_swallowed():
    # Returning None lets Django's own 500 handling take over instead of
    # dressing a programming bug up as a tidy API error.
    assert handle(ZeroDivisionError("bug")) is None
