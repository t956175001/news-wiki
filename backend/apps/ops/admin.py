from django.contrib import admin

from .models import ExtractionRun


@admin.register(ExtractionRun)
class ExtractionRunAdmin(admin.ModelAdmin):
    list_display = (
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
        "started_at",
    )
    list_filter = ("status", "trigger")
    search_fields = ("run_id", "error_message")
    date_hierarchy = "started_at"
    readonly_fields = ("started_at",)
