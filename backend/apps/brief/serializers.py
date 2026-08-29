"""Brief serializers. Contract: `docs/ARCHITECTURE.md` sections 3.4 and 4."""

from rest_framework import serializers

from .models import DailyBrief


class CitationSerializer(serializers.Serializer):
    """One entry of the reference list. Stored shape: ARCHITECTURE 3.4.

    Declared rather than left as a bare JSONField so the schema — and therefore
    the frontend's type — knows what a citation contains. The `[n]` markers in
    `content_md` refer to `index`.
    """

    index = serializers.IntegerField()
    raw_article_id = serializers.IntegerField()
    title = serializers.CharField()
    url = serializers.CharField()
    publish_time = serializers.DateTimeField(allow_null=True)


class DailyBriefListSerializer(serializers.ModelSerializer):
    """List rows without the body — an archive page needs dates, not prose."""

    citation_count = serializers.SerializerMethodField()

    class Meta:
        model = DailyBrief
        fields = ["id", "date", "title", "model_name", "citation_count", "created_at"]
        read_only_fields = fields

    def get_citation_count(self, brief: DailyBrief) -> int:
        return len(brief.citations)


class DailyBriefDetailSerializer(serializers.ModelSerializer):
    citations = CitationSerializer(many=True, read_only=True)
    run_id = serializers.CharField(source="extraction_run.run_id", default=None, read_only=True)

    class Meta:
        model = DailyBrief
        fields = [
            "id",
            "date",
            "title",
            "content_md",
            "citations",
            "model_name",
            "run_id",
            "created_at",
        ]
        read_only_fields = fields
