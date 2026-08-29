"""The cron entry point.

The rest of the ops API (run list, run detail, stats) lands in D6. This endpoint
is here now because it is the one that carries a secret.
"""

import logging
import secrets

from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.background import run_in_background
from apps.ops.services.pipeline import run_daily
from apps.wiki.services.extract_pipeline import start_run

logger = logging.getLogger(__name__)

CRON_TOKEN_HEADER = "X-Cron-Token"

FORBIDDEN_DETAIL = "无效的 cron token。"


def _token_matches(request: Request) -> bool:
    """Constant-time comparison against `CRON_TOKEN`.

    `compare_digest` rather than `==` because the comparison is against a secret
    an attacker can retry: a short-circuiting compare leaks its prefix in timing.
    """
    expected = settings.CRON_TOKEN
    if not expected:
        # Otherwise forgetting the env var would silently make the one endpoint
        # that spends money on demand public.
        logger.error("CRON_TOKEN is not configured; refusing every cron trigger")
        return False

    return secrets.compare_digest(request.headers.get(CRON_TOKEN_HEADER, ""), expected)


@extend_schema(
    summary="触发每日流水线",
    description=(
        "cron 专用：采集 → 抽取 → 简报，写进同一个 ExtractionRun。"
        "需要 `X-Cron-Token` header。免限流、免日预算熔断。"
        "立即返回 run_id，轮询 `/api/v1/ops/runs/{run_id}/` 看进度。"
    ),
    parameters=[
        OpenApiParameter(
            name=CRON_TOKEN_HEADER,
            location=OpenApiParameter.HEADER,
            required=True,
            description="与 CRON_TOKEN 环境变量比对。",
            type=str,
        )
    ],
    request=None,
    responses={202: dict, 403: dict},
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])  # PRD section 4: cron is exempt from the demo quota.
def cron_daily(request: Request) -> Response:
    if not _token_matches(request):
        logger.warning("Rejected cron trigger without a valid token")
        return Response(
            {"code": "FORBIDDEN", "detail": FORBIDDEN_DETAIL},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Created here, not in the thread, so the caller gets an id it can poll on
    # the very next request.
    run = start_run("cron")
    run_in_background(f"run-daily-{run.run_id}", run_daily, run=run, trigger="cron")

    logger.info("run_id=%s daily pipeline accepted from cron", run.run_id)
    return Response({"run_id": run.run_id, "status": run.status}, status=status.HTTP_202_ACCEPTED)
