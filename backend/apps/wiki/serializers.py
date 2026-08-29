"""Wiki serializers. The read side lands in D6; this is the write side."""

from rest_framework import serializers


class ExtractRequestSerializer(serializers.Serializer):
    """Body of `POST /api/v1/wiki/extract/`."""

    article_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        help_text="要抽取的 RawArticle id 列表。",
    )


class RunAcceptedSerializer(serializers.Serializer):
    """What an accepted long-running trigger returns: an id to poll on."""

    run_id = serializers.CharField()
    status = serializers.CharField()
