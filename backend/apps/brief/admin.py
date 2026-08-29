from django.contrib import admin

from .models import DailyBrief


@admin.register(DailyBrief)
class DailyBriefAdmin(admin.ModelAdmin):
    list_display = ("date", "title", "model_name", "extraction_run", "created_at")
    list_filter = ("model_name", "date")
    search_fields = ("title", "content_md")
    date_hierarchy = "date"
    autocomplete_fields = ("extraction_run",)
    readonly_fields = ("created_at",)
