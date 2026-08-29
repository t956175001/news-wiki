"""Read-only prompt endpoints.

Prompts are versioned in migrations and code, not edited through the API — the
observability page only needs to *show* what ran. See ADR: no online prompt
editing.
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView

from .models import PromptTemplate, PromptVersion
from .serializers import PromptTemplateSerializer, PromptVersionSerializer


@extend_schema(
    summary="Prompt 模板列表",
    description=(
        "所有 prompt 模板及其当前版本全文，只读。词条页上每条证据都记着自己是被哪个 "
        "`prompt_key` 的哪个版本抽出来的，这个端点是那串版本号对应的原文。不分页。"
    ),
)
class PromptTemplateListView(ListAPIView):
    serializer_class = PromptTemplateSerializer
    pagination_class = None
    queryset = PromptTemplate.objects.select_related("current_version").all()


@extend_schema(
    summary="Prompt 模板详情",
    description="按 `key` 取单个模板，含当前版本全文。",
)
class PromptTemplateDetailView(RetrieveAPIView):
    serializer_class = PromptTemplateSerializer
    lookup_field = "key"
    queryset = PromptTemplate.objects.select_related("current_version").all()


@extend_schema(
    summary="Prompt 历史版本",
    description="某个模板的全部版本，用于对比「v1 抽出来的」和「v2 抽出来的」有什么差别。不分页。",
)
class PromptVersionListView(ListAPIView):
    serializer_class = PromptVersionSerializer
    pagination_class = None
    # Only so drf-spectacular can infer the model; get_queryset does the work.
    queryset = PromptVersion.objects.none()

    def get_queryset(self):
        template = get_object_or_404(PromptTemplate, key=self.kwargs["key"])
        return template.versions.all()
