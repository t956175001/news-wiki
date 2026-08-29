"""Ingest endpoints: RSS sources and the raw articles pulled from them.

Read-only apart from adding a source, which is the one write here and therefore
carries the demo quota (PRD section 4).
"""

from django.db.models import Count
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.filters import OrderingFilter

from apps.common.throttling import DemoWriteThrottle

from .filters import RawArticleFilter
from .models import RawArticle, RssSource
from .serializers import RawArticleDetailSerializer, RawArticleListSerializer, RssSourceSerializer


@extend_schema_view(
    list=extend_schema(
        summary="RSS 源列表",
        description="所有已配置的采集源，含上次采集时间与错误信息。不分页。",
    ),
    create=extend_schema(
        summary="新增 RSS 源",
        description="演示模式下每个 IP 每天 3 次。新增后由下一次 cron 采集。",
    ),
)
class RssSourceViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = RssSourceSerializer
    pagination_class = None
    filter_backends = [OrderingFilter]
    ordering_fields = ["name", "last_fetched_at", "created_at"]
    queryset = RssSource.objects.annotate(article_count=Count("articles"))

    def get_throttles(self):
        # Reads are free; only adding a source spends anything the operator cares
        # about, so the quota attaches to that one action.
        if self.action == "create":
            return [DemoWriteThrottle()]
        return super().get_throttles()


@extend_schema_view(
    list=extend_schema(
        summary="原始文章列表",
        description="采集到的文章，不含正文。filter：`source`、`extract_status`；`search` 匹配标题。",
    ),
    retrieve=extend_schema(
        summary="文章详情",
        description="含正文全文与去重哈希。词条页的证据链接指向这里。",
    ),
)
class RawArticleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    filterset_class = RawArticleFilter
    # `search` is the project-wide default SearchFilter backend; scoped to the
    # title because the body is where every article mentions every company.
    search_fields = ["title"]
    ordering_fields = ["publish_time", "fetched_at"]
    queryset = RawArticle.objects.select_related("source")

    def get_serializer_class(self):
        return RawArticleDetailSerializer if self.action == "retrieve" else RawArticleListSerializer
