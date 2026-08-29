"""Ingest serializers. Contract: `docs/ARCHITECTURE.md` section 4.

Field names go out in snake_case exactly as the models spell them — the frontend
types in `src/types/` mirror these one for one and do no renaming (CLAUDE.md).
"""

from rest_framework import serializers

from .models import RawArticle, RssSource


class RssSourceSerializer(serializers.ModelSerializer):
    article_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = RssSource
        fields = [
            "id",
            "name",
            "url",
            "site_url",
            "enabled",
            "last_fetched_at",
            "last_error",
            "article_count",
            "created_at",
        ]
        read_only_fields = ["id", "last_fetched_at", "last_error", "article_count", "created_at"]


class RawArticleListSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source.name", default=None, read_only=True)

    class Meta:
        model = RawArticle
        # No `content`: a page of twenty full articles is megabytes of text the
        # list view never renders. The detail endpoint carries it.
        fields = [
            "id",
            "source",
            "source_name",
            "title",
            "url",
            "summary",
            "author",
            "publish_time",
            "lang",
            "extract_status",
            "fetched_at",
        ]
        read_only_fields = fields


class RawArticleDetailSerializer(RawArticleListSerializer):
    class Meta(RawArticleListSerializer.Meta):
        fields = [*RawArticleListSerializer.Meta.fields, "content", "content_hash"]
        read_only_fields = fields
