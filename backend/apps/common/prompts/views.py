"""Read-only prompt endpoints.

Prompts are versioned in migrations and code, not edited through the API — the
observability page only needs to *show* what ran. See ADR: no online prompt
editing.
"""

from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView, RetrieveAPIView

from .models import PromptTemplate, PromptVersion
from .serializers import PromptTemplateSerializer, PromptVersionSerializer


class PromptTemplateListView(ListAPIView):
    serializer_class = PromptTemplateSerializer
    pagination_class = None
    queryset = PromptTemplate.objects.select_related("current_version").all()


class PromptTemplateDetailView(RetrieveAPIView):
    serializer_class = PromptTemplateSerializer
    lookup_field = "key"
    queryset = PromptTemplate.objects.select_related("current_version").all()


class PromptVersionListView(ListAPIView):
    serializer_class = PromptVersionSerializer
    pagination_class = None
    # Only so drf-spectacular can infer the model; get_queryset does the work.
    queryset = PromptVersion.objects.none()

    def get_queryset(self):
        template = get_object_or_404(PromptTemplate, key=self.kwargs["key"])
        return template.versions.all()
