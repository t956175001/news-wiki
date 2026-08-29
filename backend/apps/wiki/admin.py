from django.contrib import admin

from .models import Concept, Entity, Evidence, Linkage


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("name", "entity_type", "mention_count", "confidence", "last_seen_at")
    list_filter = ("entity_type",)
    search_fields = ("name", "normalized_name", "summary")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Concept)
class ConceptAdmin(admin.ModelAdmin):
    list_display = ("name", "namespace", "confidence", "created_at")
    list_filter = ("namespace",)
    search_fields = ("name", "definition")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Linkage)
class LinkageAdmin(admin.ModelAdmin):
    list_display = ("subject_entity", "predicate", "object_entity", "object_concept", "confidence")
    list_filter = ("predicate",)
    search_fields = (
        "predicate",
        "subject_entity__name",
        "object_entity__name",
        "object_concept__name",
    )
    autocomplete_fields = ("subject_entity", "object_entity", "object_concept")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "raw_article",
        "target",
        "prompt_key",
        "prompt_version",
        "extraction_run",
        "created_at",
    )
    # RelatedOnlyFieldListFilter keeps these dropdowns to rows that actually have
    # evidence, instead of listing every article/run ever ingested.
    list_filter = (
        ("raw_article", admin.RelatedOnlyFieldListFilter),
        ("extraction_run", admin.RelatedOnlyFieldListFilter),
        "prompt_key",
        "prompt_version",
    )
    search_fields = ("snippet", "prompt_key", "raw_article__title", "extraction_run__run_id")
    autocomplete_fields = ("raw_article", "entity", "concept", "linkage", "extraction_run")
    readonly_fields = ("created_at",)

    @admin.display(description="target")
    def target(self, obj: Evidence) -> str:
        return str(obj.entity or obj.concept or obj.linkage)
