"""Ops endpoints: the run history behind the pipeline dashboard, plus the cron
entry point.

Everything here is read-only except `cron_daily`, which is the one door in this
API that spends money on request and is therefore the one that carries a secret.
"""

import logging
import secrets

from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.background import run_in_background
from apps.common.exceptions import AppError
from apps.ops.models import ExtractionRun
from apps.ops.serializers import (
    ExtractionRunDetailSerializer,
    ExtractionRunListSerializer,
    StatsSerializer,
)
from apps.ops.services.pipeline import run_daily
from apps.ops.services.stats import WINDOW_DAYS, recent_stats
from apps.wiki.services.extract_pipeline import start_run

logger = logging.getLogger(__name__)

CRON_TOKEN_HEADER = "X-Cron-Token"

FORBIDDEN_DETAIL = "无效的 cron token。"

# A year is more than any dashboard card needs, and it keeps an unbounded scan
# out of reach of a query string.
MAX_STATS_DAYS = 365


@extend_schema_view(
    list=extend_schema(
        summary="抽取记录列表",
        description="历次工作流执行，最近的在前。不含分步指标，展开某一条时再取详情。",
    ),
    retrieve=extend_schema(
        summary="抽取记录详情",
        description=(
            "含 `step_metrics`（每步的状态/耗时/token）与 `prompt_versions`（本次快照的 prompt 版本）。"
            "抽取进行中时前端轮询这个端点看进度——指标是每步写一次的，不是结束时一次性写的。"
        ),
    ),
)
class ExtractionRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    # The uuid4 hex, not the primary key: it is what every log line, every
    # Evidence row and the trigger response already quote.
    lookup_field = "run_id"
    lookup_value_regex = "[0-9a-f]{32}"
    filterset_fields = ["status", "trigger"]
    ordering_fields = ["started_at", "total_tokens", "cost_cny", "elapsed_ms"]
    queryset = ExtractionRun.objects.all()

    def get_serializer_class(self):
        return ExtractionRunDetailSerializer if self.action == "retrieve" else ExtractionRunListSerializer


class StatsView(APIView):
    """`GET /api/v1/ops/stats/` — the header cards on the pipeline dashboard."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="近 7 天聚合",
        description=(
            f"默认窗口 {WINDOW_DAYS} 天：run 数、成功率、总 token、总成本，外加按状态的分布。"
            "`success_rate` 只把 `success` 算作成功，`partial` 不算。"
        ),
        parameters=[
            OpenApiParameter("days", int, description=f"统计窗口天数，默认 {WINDOW_DAYS}。"),
        ],
        responses={200: StatsSerializer},
    )
    def get(self, request: Request) -> Response:
        days = _positive_int(request.query_params.get("days"), WINDOW_DAYS)
        return Response(StatsSerializer(recent_stats(days)).data)


def _positive_int(raw: str | None, default: int) -> int:
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise AppError(f"参数 days 必须是整数，收到 {raw!r}。", code="PARSE_ERROR") from None
    if value < 1:
        raise AppError("参数 days 必须大于 0。", code="PARSE_ERROR")
    return min(value, MAX_STATS_DAYS)


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
    summary="触发每日工作流",
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
