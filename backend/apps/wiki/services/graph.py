"""Build the relation graph payload. Contract: `docs/ARCHITECTURE.md` section 4.2.

Shaped for ECharts' `graph` series so the frontend renders the response as it
arrives. `symbolSize` is computed here rather than in the browser for the same
reason: sizing is a data decision, and two clients doing their own arithmetic
would eventually disagree about it.
"""

import logging
from collections.abc import Iterable

from django.db.models import Count, Q

from apps.wiki.models import Concept, Entity, Linkage

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 150
MAX_LIMIT = 500

# ARCHITECTURE 4.2: `min(60, 12 + value * 2)`. Small enough that a node with no
# relations is still clickable, capped so one hub does not cover the canvas.
BASE_SIZE = 12
SIZE_PER_RELATION = 2
MAX_SIZE = 60

ENTITY_PREFIX = "e"
CONCEPT_PREFIX = "c"


def symbol_size(value: int) -> int:
    return min(MAX_SIZE, BASE_SIZE + value * SIZE_PER_RELATION)


def node_id(prefix: str, pk: int) -> str:
    """`"e12"` / `"c3"` — prefixed so an entity and a concept cannot collide."""
    return f"{prefix}{pk}"


def _entity_nodes(entity_type: str | None) -> list[dict]:
    """Entities with their relation degree, ranked by how often they are mentioned."""
    queryset = Entity.objects.all()
    if entity_type:
        queryset = queryset.filter(entity_type=entity_type)

    queryset = queryset.annotate(
        degree=Count("outgoing_linkages", distinct=True) + Count("incoming_linkages", distinct=True)
    ).order_by("-mention_count", "normalized_name")

    return [
        {
            "id": node_id(ENTITY_PREFIX, entity.pk),
            "name": entity.name,
            "category": entity.entity_type,
            "value": entity.degree,
            "symbolSize": symbol_size(entity.degree),
            # Not serialised: the key the Top-N cut is made on.
            "_rank": entity.mention_count,
        }
        for entity in queryset
    ]


def _concept_nodes(namespace: str | None) -> list[dict]:
    """Concepts ranked by degree — they have no mention_count to rank by."""
    queryset = Concept.objects.all()
    if namespace:
        queryset = queryset.filter(namespace=namespace)

    queryset = queryset.annotate(degree=Count("linkages", distinct=True)).order_by("-degree", "name")

    return [
        {
            "id": node_id(CONCEPT_PREFIX, concept.pk),
            "name": concept.name,
            "category": concept.namespace,
            "value": concept.degree,
            "symbolSize": symbol_size(concept.degree),
            "_rank": concept.degree,
        }
        for concept in queryset
    ]


def _links_between(node_ids: set[str]) -> list[dict]:
    """Edges whose both ends survived the filter and the Top-N cut.

    An edge to a node that is not on the canvas would render as a line into
    nowhere, so it is dropped rather than drawn.
    """
    linkages = Linkage.objects.filter(
        Q(object_entity__isnull=False) | Q(object_concept__isnull=False)
    ).values("subject_entity_id", "predicate", "object_entity_id", "object_concept_id", "confidence")

    links = []
    for linkage in linkages:
        source = node_id(ENTITY_PREFIX, linkage["subject_entity_id"])
        if linkage["object_entity_id"] is not None:
            target = node_id(ENTITY_PREFIX, linkage["object_entity_id"])
        else:
            target = node_id(CONCEPT_PREFIX, linkage["object_concept_id"])

        if source in node_ids and target in node_ids:
            links.append(
                {
                    "source": source,
                    "target": target,
                    "predicate": linkage["predicate"],
                    "value": linkage["confidence"],
                }
            )
    return links


def _categories(nodes: Iterable[dict]) -> list[dict]:
    """The legend, in a stable order.

    ECharts colours categories by index, so the order has to be deterministic —
    otherwise the same entity is blue on one load and orange on the next. Model
    choice order first, anything unexpected appended alphabetically.
    """
    known = [choice for choice, _label in Entity.ENTITY_TYPES]
    present = {node["category"] for node in nodes}

    ordered = [name for name in known if name in present]
    ordered += sorted(present - set(ordered))
    return [{"name": name} for name in ordered]


def build_graph(
    *,
    entity_type: str | None = None,
    namespace: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """The whole graph payload in four queries, whatever the graph's size.

    Filters apply to their own kind of node: `entity_type` narrows the entities,
    `namespace` narrows the concepts. Isolated nodes are kept — a filtered-in
    entity with no relations is still a true answer to "what is there".
    """
    limit = max(1, min(limit, MAX_LIMIT))

    nodes = _entity_nodes(entity_type) + _concept_nodes(namespace)
    truncated = len(nodes) > limit
    if truncated:
        # Top-N by prominence: mention_count for entities, degree for concepts.
        nodes.sort(key=lambda node: (-node["_rank"], node["name"]))
        nodes = nodes[:limit]
        logger.info("Graph truncated to %s nodes (limit=%s)", len(nodes), limit)

    for node in nodes:
        del node["_rank"]

    return {
        "nodes": nodes,
        "links": _links_between({node["id"] for node in nodes}),
        "categories": _categories(nodes),
        "truncated": truncated,
    }
