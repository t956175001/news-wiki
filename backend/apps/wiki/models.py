"""Wiki models: entities, concepts, the relations between them, and the evidence
that backs every one of those claims.

Field contract: `docs/ARCHITECTURE.md` section 3.2.
"""

from django.db import models
from django.db.models import Q


class Entity(models.Model):
    ENTITY_TYPES = [
        ("person", "Person"),
        ("org", "Organization"),
        ("product", "Product"),
        ("model", "Model"),
        ("tech", "Technology"),
        ("event", "Event"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPES)
    aliases = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)
    confidence = models.FloatField(default=1.0)
    mention_count = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-mention_count", "normalized_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_name", "entity_type"],
                name="uniq_entity_norm_type",
            )
        ]
        indexes = [models.Index(fields=["entity_type"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.entity_type})"


class Concept(models.Model):
    name = models.CharField(max_length=255)
    namespace = models.CharField(max_length=80)
    definition = models.TextField(blank=True)
    signals = models.JSONField(default=list, blank=True)
    confidence = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["namespace", "name"]
        constraints = [models.UniqueConstraint(fields=["namespace", "name"], name="uniq_concept_ns_name")]

    def __str__(self) -> str:
        return f"{self.namespace}/{self.name}"


class Linkage(models.Model):
    subject_entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="outgoing_linkages")
    predicate = models.CharField(max_length=80)
    object_entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="incoming_linkages",
        null=True,
        blank=True,
    )
    object_concept = models.ForeignKey(
        Concept,
        on_delete=models.CASCADE,
        related_name="linkages",
        null=True,
        blank=True,
    )
    confidence = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(object_entity__isnull=False) | Q(object_concept__isnull=False),
                name="linkage_object_required",
            ),
            models.UniqueConstraint(
                fields=["subject_entity", "predicate", "object_entity", "object_concept"],
                name="uniq_linkage_triple",
            ),
        ]

    def __str__(self) -> str:
        obj = self.object_entity or self.object_concept
        return f"{self.subject_entity_id} -{self.predicate}-> {obj}"


class Evidence(models.Model):
    """一条 Evidence 只能指向 entity / concept / linkage 三者之一。"""

    raw_article = models.ForeignKey("ingest.RawArticle", on_delete=models.CASCADE, related_name="evidences")
    entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, null=True, blank=True, related_name="evidences"
    )
    concept = models.ForeignKey(
        Concept, on_delete=models.CASCADE, null=True, blank=True, related_name="evidences"
    )
    linkage = models.ForeignKey(
        Linkage, on_delete=models.CASCADE, null=True, blank=True, related_name="evidences"
    )
    snippet = models.TextField()
    extraction_run = models.ForeignKey(
        "ops.ExtractionRun", on_delete=models.CASCADE, related_name="evidences"
    )
    prompt_key = models.CharField(max_length=100)
    prompt_version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(entity__isnull=False, concept__isnull=True, linkage__isnull=True)
                    | Q(entity__isnull=True, concept__isnull=False, linkage__isnull=True)
                    | Q(entity__isnull=True, concept__isnull=True, linkage__isnull=False)
                ),
                name="evidence_single_target",
            )
        ]

    def __str__(self) -> str:
        return f"Evidence #{self.pk} ({self.prompt_key} v{self.prompt_version})"
