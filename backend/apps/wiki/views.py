"""Manual extraction trigger.

The read side of the wiki API (entities, concepts, graph) lands in D6. This
endpoint is here now because it is the only write the public demo exposes, and
both guard rails it carries — the per-IP throttle and the daily budget — are the
point of D5.
"""

import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.background import run_in_background
from apps.common.budget import check_budget
from apps.common.exceptions import AppError
from apps.common.throttling import DemoWriteThrottle
from apps.ingest.models import RawArticle
from apps.wiki.serializers import ExtractRequestSerializer, RunAcceptedSerializer
from apps.wiki.services.extract_pipeline import run_extraction, start_run

logger = logging.getLogger(__name__)

TRIGGER = "manual"


class ExtractView(APIView):
    """`POST /api/v1/wiki/extract/` — run the three-step pipeline over some articles."""

    permission_classes = [AllowAny]
    throttle_classes = [DemoWriteThrottle]

    @extend_schema(
        summary="手动触发抽取",
        description=(
            "对指定文章跑实体 → 概念 → 关系三步抽取。演示模式下每个 IP 每天 3 次，"
            "超出当日 LLM 预算时返回 503。立即返回 run_id，"
            "轮询 `/api/v1/ops/runs/{run_id}/` 看进度。"
        ),
        request=ExtractRequestSerializer,
        responses={202: RunAcceptedSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = ExtractRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Checked here as well as inside the pipeline: the pipeline's check runs
        # on a background thread where nobody can see the 503.
        check_budget(TRIGGER)

        articles = list(RawArticle.objects.filter(pk__in=serializer.validated_data["article_ids"]))
        if not articles:
            raise AppError("没有找到这些 id 对应的文章。", code="NO_ARTICLES")

        run = start_run(TRIGGER, articles_in=len(articles))
        run_in_background(f"extract-{run.run_id}", run_extraction, articles, TRIGGER, run=run)

        logger.info("run_id=%s manual extraction accepted for %s article(s)", run.run_id, len(articles))
        return Response({"run_id": run.run_id, "status": run.status}, status=status.HTTP_202_ACCEPTED)
