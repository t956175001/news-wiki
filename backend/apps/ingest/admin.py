from django.contrib import admin

from .models import RawArticle, RssSource


@admin.register(RssSource)
class RssSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "url", "enabled", "last_fetched_at", "has_error", "created_at")
    list_filter = ("enabled",)
    search_fields = ("name", "url", "site_url")
    readonly_fields = ("created_at",)
    list_editable = ("enabled",)

    @admin.display(boolean=True, description="error")
    def has_error(self, obj: RssSource) -> bool:
        return bool(obj.last_error)


@admin.register(RawArticle)
class RawArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "extract_status", "publish_time", "fetched_at", "lang")
    list_filter = ("extract_status", "lang", "source")
    search_fields = ("title", "url", "author", "content_hash")
    date_hierarchy = "fetched_at"
    readonly_fields = ("content_hash", "fetched_at")
    autocomplete_fields = ("source",)
