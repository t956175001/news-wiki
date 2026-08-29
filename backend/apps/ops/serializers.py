"""Ops serializers. Contract: `docs/ARCHITECTURE.md` sections 3.3 and 4."""

from rest_framework import serializers

from .models import ExtractionRun

_LIST_FIELDS = [
    "run_id",
    "status",
    "trigger",
    "articles_in",
    "entities_saved",
    "concepts_saved",
    "linkages_saved",
    "total_tokens",
    "cost_cny",
    "elapsed_ms",
    "error_message",
    "started_at",
    "finished_at",
]


class ExtractionRunListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractionRun
        # No `step_metrics`: the table shows one row per run and only expands one
        # at a time, so per-step detail belongs to the detail endpoint.
        fields = _LIST_FIELDS
        read_only_fields = fields


class ExtractionRunDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractionRun
        fields = [*_LIST_FIELDS, "prompt_tokens", "completion_tokens", "step_metrics", "prompt_versions"]
        read_only_fields = fields


class StatsSerializer(serializers.Serializer):
    """Header cards on `/ops`. Shape produced by `services/stats.py`."""

    window_days = serializers.IntegerField()
    since = serializers.DateTimeField()
    total_runs = serializers.IntegerField()
    success_runs = serializers.IntegerField(help_text="status 为 success 的 run 数，不含 partial。")
    success_rate = serializers.FloatField(help_text="0-1 的小数，无 run 时为 0。")
    total_tokens = serializers.IntegerField()
    total_cost_cny = serializers.DecimalField(max_digits=12, decimal_places=4)
    by_status = serializers.DictField(child=serializers.IntegerField())
