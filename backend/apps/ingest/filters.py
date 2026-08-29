"""Ingest filters. Query params are part of the API contract (section 4)."""

from django_filters import rest_framework as filters

from .models import RawArticle


class RawArticleFilter(filters.FilterSet):
    class Meta:
        model = RawArticle
        fields = ["source", "extract_status"]
