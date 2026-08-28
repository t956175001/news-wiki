"""DRF `EXCEPTION_HANDLER`: collapse every error into `{"code", "detail"}`.

Field-level validation errors keep their per-field messages under `fields`, so
the frontend can still highlight inputs without parsing free text.
"""

from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.common.exceptions import AppError

_CODE_TO_STATUS: dict[str, int] = {
    "APP_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "FETCH_ERROR": status.HTTP_502_BAD_GATEWAY,
    "LLM_ERROR": status.HTTP_502_BAD_GATEWAY,
    "PARSE_ERROR": status.HTTP_400_BAD_REQUEST,
    "PROMPT_RENDER_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
    # Not the caller's fault and not permanent — the daily cap resets tomorrow.
    "BUDGET_EXCEEDED": status.HTTP_503_SERVICE_UNAVAILABLE,
}

DEMO_THROTTLED_DETAIL = "演示模式下每个 IP 每天可触发 3 次实时抽取，明天再来试试～"


def custom_exception_handler(exc, context):
    if isinstance(exc, AppError):
        http_status = _CODE_TO_STATUS.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        data: dict = {"code": exc.code, "detail": exc.detail}
        if exc.fields is not None:
            data["fields"] = exc.fields
        return Response(data, status=http_status)

    if isinstance(exc, Throttled):
        return Response(
            {"code": "RATE_LIMITED", "detail": DEMO_THROTTLED_DETAIL},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    response = exception_handler(exc, context)
    if response is None:
        return None

    payload = response.data
    if isinstance(payload, dict) and "detail" in payload:
        detail = str(payload["detail"])
        code = getattr(payload["detail"], "code", "error")
    elif isinstance(payload, list):
        detail = "; ".join(str(item) for item in payload)
        code = "error"
    else:
        detail = str(payload)
        code = "error"

    fields = None
    if isinstance(payload, dict):
        fields = {
            key: [str(item) for item in (value if isinstance(value, list) else [value])]
            for key, value in payload.items()
            if key != "detail"
        }

    response.data = {"code": code, "detail": detail}
    if fields:
        response.data["fields"] = fields

    return response
