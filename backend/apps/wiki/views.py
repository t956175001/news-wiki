"""Wiki endpoints: entities, concepts, the graph, and the manual extract trigger.

The entry detail endpoint is the one this project is judged on. It answers the
whole page — relations, evidence, sources, prompt versions — in five queries,
fixed, no matter how many relations the entity has. The `Prefetch` objects below
are what makes that true; changing them is how this page becomes an N+1.
"""

import logging

from django.db.models import Prefetch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.background import run_in_background
from apps.common.budget import check_budget
from apps.common.exceptions import AppError
from apps.common.throttling import DemoWriteThrottle
from apps.ingest.models import RawArticle
from apps.wiki.filters import ConceptFilter, EntityFilter
from apps.wiki.models import Concept, Entity, Evidence, Linkage
from apps.wiki.serializers import (
    ConceptDetailSerializer,
    ConceptListSerializer,
    EntityDetailSerializer,
    EntityListSerializer,
    ExtractRequestSerializer,
    GraphSerializer,
    RunAcceptedSerializer,
)
from apps.wiki.services.extract_pipeline import run_extraction, start_run
from apps.wiki.services.graph import DEFAULT_LIMIT, build_graph

logger = logging.getLogger(__name__)

TRIGGER = "manual"


def _evidence_queryset():
    """Evidence with its article, that article's source, and the run, in one go.

    Newest first with the id as a tiebreaker: a batch is written by one
    `bulk_create` inside a transaction, so `created_at` alone is not a total
    order and the page would shuffle between reloads.
    """
    return Evidence.objects.select_related("raw_article", "raw_article__source", "extraction_run").order_by(
        "-created_at", "-id"
    )


def _linkages(*, incoming: bool):
    """One side of an entity's edges, with the far node and evidence attached."""
    related = ["subject_entity"] if incoming else ["object_entity", "object_concept"]
    return Linkage.objects.select_related(*related).prefetch_related(
        Prefetch("evidences", queryset=_evidence_queryset())
    )


def entity_detail_queryset():
    """The five-query entry page: entity, two edge sets, evidence for each."""
    return Entity.objects.prefetch_related(
        Prefetch("outgoing_linkages", queryset=_linkages(incoming=False)),
        Prefetch("incoming_linkages", queryset=_linkages(incoming=True)),
    )


@extend_schema_view(
    list=extend_schema(
        summary="实体列表",
        description="按提及次数倒序。filter：`entity_type`；`search` 匹配名称与别名。",
    ),
    retrieve=extend_schema(
        summary="词条详情 ★",
        description=(
            "词条页的唯一数据来源：实体本身 + 出边入边合并的 `linkages` 数组，"
            "每条关系挂着原文证据、来源文章、置信度、抽取用的 prompt 版本和 run_id。"
            "`direction` 为 `out` 时本实体是主语，`in` 时是宾语；`object` 始终是关系的另一端。"
        ),
    ),
)
class EntityViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    filterset_class = EntityFilter
    ordering_fields = ["mention_count", "confidence", "last_seen_at", "name"]
    queryset = Entity.objects.all()

    def get_queryset(self):
        return entity_detail_queryset() if self.action == "retrieve" else Entity.objects.all()

    def get_serializer_class(self):
        return EntityDetailSerializer if self.action == "retrieve" else EntityListSerializer


@extend_schema_view(
    list=extend_schema(
        summary="概念列表",
        description="filter：`namespace`；`search` 匹配名称与信号词。",
    ),
    retrieve=extend_schema(
        summary="概念详情",
        description=("结构与词条详情一致。概念只会作为关系的宾语出现，所以 `linkages` 全是 `direction=in`。"),
    ),
)
class ConceptViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    filterset_class = ConceptFilter
    ordering_fields = ["name", "confidence"]
    queryset = Concept.objects.all()

    def get_queryset(self):
        if self.action == "retrieve":
            return Concept.objects.prefetch_related(Prefetch("linkages", queryset=_linkages(incoming=True)))
        return Concept.objects.all()

    def get_serializer_class(self):
        return ConceptDetailSerializer if self.action == "retrieve" else ConceptListSerializer


class GraphView(APIView):
    """`GET /api/v1/wiki/graph/` — the whole graph, shaped for ECharts."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="关系图谱",
        description=(
            "直接对齐 ECharts `graph` 系列，前端不做转换。`symbolSize` 由后端算好"
            "（`min(60, 12 + value*2)`），`value` 是该节点连着的关系数。"
            "节点总数超过 `limit` 时按提及次数取 Top-N，并置 `truncated=true`。"
        ),
        parameters=[
            OpenApiParameter(
                "entity_type", OpenApiTypes.STR, description="只保留这些类型的实体节点，逗号分隔可传多个。"
            ),
            OpenApiParameter(
                "namespace", OpenApiTypes.STR, description="只保留这些命名空间的概念节点，逗号分隔可传多个。"
            ),
            OpenApiParameter("limit", OpenApiTypes.INT, description=f"节点数上限，默认 {DEFAULT_LIMIT}。"),
        ],
        responses={200: GraphSerializer},
    )
    def get(self, request: Request) -> Response:
        return Response(
            build_graph(
                entity_type=_list_param(request, "entity_type"),
                namespace=_list_param(request, "namespace"),
                limit=_int_param(request, "limit", DEFAULT_LIMIT),
            )
        )


def _list_param(request: Request, name: str) -> list[str] | None:
    """A comma-separated query param, e.g. `entity_type=org,product`. Empty → None."""
    raw = request.query_params.get(name)
    if not raw:
        return None
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or None


def _int_param(request: Request, name: str, default: int) -> int:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise AppError(f"参数 {name} 必须是整数，收到 {raw!r}。", code="PARSE_ERROR") from None


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
