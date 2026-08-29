"""Wiki serializers. Contract: `docs/ARCHITECTURE.md` sections 4, 4.1 and 4.2.

`EntityDetailSerializer` is the one that matters. The entry page is built from
this single response — relations, evidence, sources, prompt versions and all —
because splitting it into follow-up requests would make the page's central claim
("every statement here is traceable") arrive one network round trip late.

Every field name here is copied from section 4.1 verbatim. The frontend types
are written against that JSON, so a rename here is a broken page there.
"""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.ingest.models import RawArticle

from .models import Concept, Entity, Evidence, Linkage


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


# --- evidence -----------------------------------------------------------


class EvidenceArticleSerializer(serializers.ModelSerializer):
    """The source card under a piece of evidence. Section 4.1 `article`."""

    source_name = serializers.CharField(source="source.name", default=None, read_only=True)

    class Meta:
        model = RawArticle
        fields = ["id", "title", "url", "publish_time", "source_name"]
        read_only_fields = fields


class EvidenceSerializer(serializers.ModelSerializer):
    """One quoted passage plus everything needed to check it.

    `prompt_key` and `prompt_version` travel with the quote rather than being
    looked up live: they record which prompt produced *this* claim, and a later
    prompt edit must not relabel it.
    """

    run_id = serializers.CharField(source="extraction_run.run_id", read_only=True)
    article = EvidenceArticleSerializer(source="raw_article", read_only=True)

    class Meta:
        model = Evidence
        fields = ["id", "snippet", "prompt_key", "prompt_version", "run_id", "article"]
        read_only_fields = fields


# --- linkages -----------------------------------------------------------


class LinkageObjectSerializer(serializers.Serializer):
    """The node at the other end of a relation. Section 4.1 `object`.

    A discriminated union on `kind`: entities carry `entity_type`, concepts carry
    `namespace`. Deliberately not both-with-nulls — the frontend switches on
    `kind`, and a null `namespace` on every entity would just be noise.
    """

    kind = serializers.ChoiceField(choices=["entity", "concept"])
    id = serializers.IntegerField()
    name = serializers.CharField()
    entity_type = serializers.CharField(required=False)
    namespace = serializers.CharField(required=False)


class LinkageSerializer(serializers.Serializer):
    """One relation as the entry page renders it. Section 4.1 `linkages[]`.

    `direction` is `"out"` when this entity is the subject and `"in"` when it is
    the object. `object` always holds the *other* end of the edge, so an in-edge
    reads "`object.name` -[predicate]-> this entity" with no further lookups.
    """

    id = serializers.IntegerField()
    direction = serializers.ChoiceField(choices=["out", "in"])
    predicate = serializers.CharField()
    object = LinkageObjectSerializer()
    confidence = serializers.FloatField()
    evidences = EvidenceSerializer(many=True)


def _object_payload(target) -> dict:
    if isinstance(target, Concept):
        return {
            "kind": "concept",
            "id": target.pk,
            "name": target.name,
            "namespace": target.namespace,
        }
    return {
        "kind": "entity",
        "id": target.pk,
        "name": target.name,
        "entity_type": target.entity_type,
    }


def linkage_payload(linkage: Linkage, direction: str) -> dict:
    """Flatten a Linkage into the section 4.1 shape.

    Reads only prefetched relations — `linkage.evidences.all()` and the two
    object FKs — so building a whole entry costs no queries beyond the five the
    viewset already issued.
    """
    other = linkage.subject_entity if direction == "in" else (linkage.object_entity or linkage.object_concept)
    return {
        "id": linkage.pk,
        "direction": direction,
        "predicate": linkage.predicate,
        "object": _object_payload(other),
        "confidence": linkage.confidence,
        "evidences": EvidenceSerializer(linkage.evidences.all(), many=True).data,
    }


def _sorted_linkages(payloads: list[dict]) -> list[dict]:
    """Group by predicate, best-supported first, out-edges before in-edges.

    The entry page groups relations by predicate (PRD 3.2); doing the sort here
    means it can walk the array once instead of bucketing it. Sorting in Python
    over the prefetched lists rather than in SQL keeps the query count flat.
    """
    return sorted(
        payloads,
        key=lambda item: (item["predicate"], item["direction"] != "out", -item["confidence"], item["id"]),
    )


# --- entities -----------------------------------------------------------


class EntityListSerializer(serializers.ModelSerializer):
    entity_type_display = serializers.CharField(source="get_entity_type_display", read_only=True)

    class Meta:
        model = Entity
        fields = [
            "id",
            "name",
            "entity_type",
            "entity_type_display",
            "aliases",
            "summary",
            "confidence",
            "mention_count",
            "first_seen_at",
            "last_seen_at",
        ]
        read_only_fields = fields


class EntityDetailSerializer(EntityListSerializer):
    """Section 4.1, exactly. Out-edges and in-edges merged into one array."""

    linkages = serializers.SerializerMethodField()

    class Meta(EntityListSerializer.Meta):
        fields = [*EntityListSerializer.Meta.fields, "linkages"]
        read_only_fields = fields

    @extend_schema_field(LinkageSerializer(many=True))
    def get_linkages(self, entity: Entity) -> list[dict]:
        payloads = [linkage_payload(link, "out") for link in entity.outgoing_linkages.all()]
        payloads += [linkage_payload(link, "in") for link in entity.incoming_linkages.all()]
        return _sorted_linkages(payloads)


# --- concepts -----------------------------------------------------------


class ConceptListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Concept
        fields = ["id", "name", "namespace", "definition", "signals", "confidence"]
        read_only_fields = fields


class ConceptDetailSerializer(ConceptListSerializer):
    """Same relation shape as an entity, minus the out-edges.

    A concept is only ever the object of a relation (`Linkage.object_concept`),
    so every edge it has is an in-edge.
    """

    linkages = serializers.SerializerMethodField()

    class Meta(ConceptListSerializer.Meta):
        fields = [*ConceptListSerializer.Meta.fields, "linkages"]
        read_only_fields = fields

    @extend_schema_field(LinkageSerializer(many=True))
    def get_linkages(self, concept: Concept) -> list[dict]:
        return _sorted_linkages([linkage_payload(link, "in") for link in concept.linkages.all()])


# --- graph --------------------------------------------------------------


class GraphNodeSerializer(serializers.Serializer):
    """Section 4.2. Shaped for ECharts `graph`; the frontend does no conversion."""

    id = serializers.CharField(help_text='`"e"+entity_id` 或 `"c"+concept_id`。')
    name = serializers.CharField()
    category = serializers.CharField(help_text="实体是 entity_type，概念是 namespace。")
    value = serializers.IntegerField(help_text="该节点连着的关系数。")
    symbolSize = serializers.IntegerField()  # noqa: N815 - ECharts spells it this way


class GraphLinkSerializer(serializers.Serializer):
    source = serializers.CharField()
    target = serializers.CharField()
    predicate = serializers.CharField()
    value = serializers.FloatField(help_text="关系的置信度。")


class GraphCategorySerializer(serializers.Serializer):
    name = serializers.CharField()


class GraphSerializer(serializers.Serializer):
    nodes = GraphNodeSerializer(many=True)
    links = GraphLinkSerializer(many=True)
    categories = GraphCategorySerializer(many=True)
    truncated = serializers.BooleanField(help_text="节点数超过 limit，只返回了 Top-N。")
