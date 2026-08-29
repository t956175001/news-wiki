"""Brief endpoints: the archive, the newest issue, and one issue by date."""

import datetime as dt

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView

from apps.common.exceptions import AppError

from .models import DailyBrief
from .serializers import DailyBriefDetailSerializer, DailyBriefListSerializer


@extend_schema(
    summary="简报列表",
    description="按日期倒序，不含正文。用于归档页与「最近一期」的日期标注。",
)
class DailyBriefListView(ListAPIView):
    serializer_class = DailyBriefListSerializer
    queryset = DailyBrief.objects.all()


@extend_schema(
    summary="最新一期简报",
    description=(
        "含正文与引用列表。首页用它：当日还没有简报时返回最近一期，"
        "前端照 `date` 字段标注这是哪一天的。一期都没有时返回 404。"
    ),
    responses={200: DailyBriefDetailSerializer, 404: OpenApiTypes.OBJECT},
)
class DailyBriefLatestView(RetrieveAPIView):
    serializer_class = DailyBriefDetailSerializer
    queryset = DailyBrief.objects.select_related("extraction_run")

    def get_object(self) -> DailyBrief:
        brief = self.get_queryset().first()
        if brief is None:
            raise AppError("还没有生成过任何简报。", code="NO_BRIEF")
        return brief


@extend_schema(
    summary="指定日期的简报",
    description="`date` 格式 `YYYY-MM-DD`。含正文与引用列表。",
    parameters=[OpenApiParameter("date", OpenApiTypes.DATE, OpenApiParameter.PATH)],
    responses={200: DailyBriefDetailSerializer, 404: OpenApiTypes.OBJECT},
)
class DailyBriefByDateView(RetrieveAPIView):
    serializer_class = DailyBriefDetailSerializer
    queryset = DailyBrief.objects.select_related("extraction_run")

    def get_object(self) -> DailyBrief:
        # The URL pattern already constrains the shape, so anything reaching here
        # is well formed; `fromisoformat` still rejects 2026-02-31.
        try:
            date = dt.date.fromisoformat(self.kwargs["date"])
        except ValueError:
            raise AppError(f"{self.kwargs['date']} 不是合法日期。", code="PARSE_ERROR") from None
        return get_object_or_404(self.get_queryset(), date=date)
