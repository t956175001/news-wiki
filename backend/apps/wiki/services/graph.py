"""Build the relation graph payload. Contract: `docs/ARCHITECTURE.md` section 4.2.

Shaped for ECharts' `graph` series so the frontend renders the response as it
arrives. `symbolSize` is computed here rather than in the browser for the same
reason: sizing is a data decision, and two clients doing their own arithmetic
would eventually disagree about it.

Two selection rules do most of the work here, both added after the first
version shipped a canvas that was 63% dots with no lines (see ADR-015):

* **Rank by degree, not `mention_count`.** `mention_count` is 1 for almost
  every entity — a day's articles rarely mention the same thing twice — so
  ranking by it made "Top-150" an arbitrary slice that cut the hubs.
* **Drop degree-0 nodes by default.** A node with no edges contributes nothing
  to a relation graph; it is a list entry that wandered onto the wrong page.
"""

import logging
from collections import Counter, deque
from collections.abc import Iterable
from datetime import timedelta

from django.db.models import Max, Q
from django.utils import timezone

from apps.wiki.models import Concept, Entity, Linkage

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

# ARCHITECTURE 4.2: `min(60, 12 + value * 2)`. Small enough that a node with no
# relations is still clickable, capped so one hub does not cover the canvas.
BASE_SIZE = 12
SIZE_PER_RELATION = 2
MAX_SIZE = 60

ENTITY_PREFIX = "e"
CONCEPT_PREFIX = "c"

DEFAULT_MIN_DEGREE = 1
DEFAULT_DEPTH = 1
MAX_DEPTH = 3

# Predicates hidden unless the caller asks for them back. `涉及` is the only one
# here and it earned its place empirically: on the live graph it labelled 17% of
# all edges (99 of 583), and "A is involved with B" is the absence of a relation
# rather than one — it is what the model reaches for when it has nothing
# specific to say. See ADR-019.
DEFAULT_EXCLUDED_PREDICATES: tuple[str, ...] = ("涉及",)

# How far back the graph looks, in days. 0 means the whole history.
#
# Without a window this graph is cumulative: it grows by roughly nine nodes per
# extracted article and nothing ever leaves, so over months the same all-time
# hubs crowd out whatever happened this week. The window is measured on the
# *article's* publish time, not on when extraction happened — the backlog is
# drained newest-first and can run days behind, so `Linkage.created_at` would
# report a two-month-old story as today's news. See ADR-019.
DEFAULT_DAYS = 30


def symbol_size(value: int) -> int:
    return min(MAX_SIZE, BASE_SIZE + value * SIZE_PER_RELATION)


def node_id(prefix: str, pk: int) -> str:
    """`"e12"` / `"c3"` — prefixed so an entity and a concept cannot collide."""
    return f"{prefix}{pk}"


def _degrees(edges: Iterable[dict]) -> Counter:
    """How many *visible* edges each node has.

    Counted from the filtered edge list rather than from the database, because
    `value` is what sizes a node and what the Top-N cut ranks on. Reading it off
    the full table while drawing a filtered graph would render a node fat and
    important-looking with a single line attached to it.
    """
    degrees: Counter = Counter()
    for edge in edges:
        degrees[edge["source"]] += 1
        degrees[edge["target"]] += 1
    return degrees


def _entity_nodes(entity_types: list[str] | None, degrees: Counter) -> list[dict]:
    """Entities with their visible relation degree, ranked by that degree."""
    queryset = Entity.objects.all()
    if entity_types:
        queryset = queryset.filter(entity_type__in=entity_types)

    nodes = []
    for entity in queryset.only("pk", "name", "entity_type", "mention_count", "normalized_name"):
        identifier = node_id(ENTITY_PREFIX, entity.pk)
        degree = degrees[identifier]
        nodes.append(
            {
                "id": identifier,
                "name": entity.name,
                "category": entity.entity_type,
                "value": degree,
                "symbolSize": symbol_size(degree),
                # Not serialised: the keys the Top-N cut is made on. Degree first —
                # this is a relation graph, so how connected a node is *is* how
                # important it is here. mention_count only breaks ties.
                "_rank": (degree, entity.mention_count),
            }
        )
    nodes.sort(key=lambda node: (-node["_rank"][0], -node["_rank"][1], node["name"]))
    return nodes


def _concept_nodes(namespaces: list[str] | None, degrees: Counter) -> list[dict]:
    """Concepts ranked by degree — they have no mention_count to rank by."""
    queryset = Concept.objects.all()
    if namespaces:
        queryset = queryset.filter(namespace__in=namespaces)

    nodes = []
    for concept in queryset.only("pk", "name", "namespace"):
        identifier = node_id(CONCEPT_PREFIX, concept.pk)
        degree = degrees[identifier]
        nodes.append(
            {
                "id": identifier,
                "name": concept.name,
                "category": concept.namespace,
                "value": degree,
                "symbolSize": symbol_size(degree),
                "_rank": (degree, 0),
            }
        )
    nodes.sort(key=lambda node: (-node["_rank"][0], node["name"]))
    return nodes


def _all_edges(exclude_predicates: Iterable[str], days: int) -> list[dict]:
    """Relations that have an object, a predicate worth drawing, and a source
    recent enough to still count.

    One query. The graph is small enough (hundreds of edges) that filtering in
    Python beats issuing a query per selection rule.
    """
    queryset = Linkage.objects.filter(Q(object_entity__isnull=False) | Q(object_concept__isnull=False))

    excluded = {predicate for predicate in exclude_predicates}
    if excluded:
        queryset = queryset.exclude(predicate__in=excluded)

    if days > 0:
        cutoff = timezone.now() - timedelta(days=days)
        # Latest source, so one recent article keeps a relation current even
        # when its other sources are old. `isnull` covers the two undateable
        # cases — no evidence at all, or evidence on articles that arrived
        # without a parseable date — and those are *kept*: the window exists to
        # retire old news, not to hide relations whose age cannot be
        # established. Only provably stale edges come out.
        queryset = queryset.annotate(latest_source=Max("evidences__raw_article__publish_time")).filter(
            Q(latest_source__gte=cutoff) | Q(latest_source__isnull=True)
        )

    linkages = queryset.values(
        "subject_entity_id", "predicate", "object_entity_id", "object_concept_id", "confidence"
    ).distinct()  # the evidence join multiplies rows; one relation is one edge

    edges = []
    for linkage in linkages:
        if linkage["object_entity_id"] is not None:
            target = node_id(ENTITY_PREFIX, linkage["object_entity_id"])
        else:
            target = node_id(CONCEPT_PREFIX, linkage["object_concept_id"])
        edges.append(
            {
                "source": node_id(ENTITY_PREFIX, linkage["subject_entity_id"]),
                "target": target,
                "predicate": linkage["predicate"],
                "value": linkage["confidence"],
            }
        )
    return edges


def _links_between(edges: list[dict], node_ids: set[str]) -> list[dict]:
    """Edges whose both ends survived the filter and the Top-N cut.

    An edge to a node that is not on the canvas would render as a line into
    nowhere, so it is dropped rather than drawn.
    """
    return [edge for edge in edges if edge["source"] in node_ids and edge["target"] in node_ids]


def _select_connected(nodes: list[dict], edges: list[dict], limit: int, pinned: str | None) -> list[dict]:
    """Pick at most `limit` nodes that still have edges once drawn.

    Taking the top `limit` nodes by degree is not enough on its own, and the
    reason is easy to miss: a hub's neighbours are mostly leaves, the leaves
    fall below the cut, and the hub arrives on the canvas with nothing attached
    to it. Measured on the demo corpus, a straight degree cut at limit=150 left
    52 of 150 nodes with no visible edge.

    So the budget is spent on *edges*: walk them best-connected first and admit
    both endpoints while there is room. Every node that gets in arrives with at
    least one edge, which is the only kind of node a relation graph is for.
    """
    candidates = {node["id"]: node for node in nodes}
    degree = {node_id: node["_rank"][0] for node_id, node in candidates.items()}

    # The ego graph's centre is admitted before any edge is considered — it is
    # the node the caller named, and it stays even if it is a lone dot.
    chosen: set[str] = {pinned} if pinned in candidates else set()

    usable = [edge for edge in edges if edge["source"] in candidates and edge["target"] in candidates]
    usable.sort(
        key=lambda edge: (-(degree[edge["source"]] + degree[edge["target"]]), edge["source"], edge["target"])
    )

    for edge in usable:
        if len(chosen) >= limit:
            break
        needed = {edge["source"], edge["target"]} - chosen
        # `continue`, not `break`: a later edge may need only one new node and
        # still fit in the room this one could not use.
        if len(chosen) + len(needed) <= limit:
            chosen |= needed

    if not chosen:
        # No edge fits. Either the budget is smaller than one edge (limit=1), or
        # the filters kept a set of nodes whose relations all point outside it —
        # `?entity_type=product` on products that only relate to orgs, say.
        # Showing the best-ranked nodes beats showing an empty canvas, even
        # though they will render unconnected.
        return nodes[:limit]

    # Preserve the incoming order (degree-descending) rather than set order.
    return [node for node in nodes if node["id"] in chosen]


def _neighbourhood(edges: list[dict], center: str, depth: int) -> set[str]:
    """Node ids within `depth` hops of `center`, following edges either way.

    Relation direction is a property of the predicate, not of relevance: if the
    page is "what is connected to OpenAI", `GPT-5 -[属于]-> OpenAI` belongs on
    it just as much as the reverse.
    """
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge["source"], set()).add(edge["target"])
        adjacency.setdefault(edge["target"], set()).add(edge["source"])

    seen = {center}
    frontier = deque([(center, 0)])
    while frontier:
        node, hops = frontier.popleft()
        if hops >= depth:
            continue
        for neighbour in adjacency.get(node, ()):
            if neighbour not in seen:
                seen.add(neighbour)
                frontier.append((neighbour, hops + 1))
    return seen


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
    entity_type: list[str] | None = None,
    namespace: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    min_degree: int = DEFAULT_MIN_DEGREE,
    center: str | None = None,
    depth: int = DEFAULT_DEPTH,
    exclude_predicate: list[str] | None = None,
    days: int = DEFAULT_DAYS,
) -> dict:
    """The whole graph payload in four queries, whatever the graph's size.

    Filters apply to their own kind of node: `entity_type` narrows the entities,
    `namespace` narrows the concepts. Either accepts more than one value — the
    frontend's filter panel is a multi-select — so a node passes if it matches
    any value in the given list.

    `min_degree` drops nodes with fewer relations than that; the default of 1
    means isolated nodes are hidden. Pass 0 to get every node that matched the
    filters, which is the honest answer to "what is in the database" even
    though it is a poor answer to "what is related to what".

    `center` switches to an ego graph: only nodes within `depth` hops of that
    node id (`"e12"` / `"c3"`). The centre itself is always kept, even when its
    degree is below `min_degree` — the caller asked for that node by name.
    An unknown centre yields an empty graph rather than an error, so a deep
    link to an entry that was later merged away degrades quietly.

    `exclude_predicate` drops edges by predicate; `None` means the default set
    (see `DEFAULT_EXCLUDED_PREDICATES`), an empty list means keep everything.
    Degrees are then counted from what is left, so hiding a predicate shrinks
    the nodes that hung off it and can drop them entirely.

    `days` keeps only relations backed by an article published within that many
    days; 0 lifts the window entirely. Same rule as above — degrees follow the
    surviving edges, so an entity whose news has aged out leaves the canvas
    rather than sitting there as a dot.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    min_degree = max(0, min_degree)
    depth = max(1, min(depth, MAX_DEPTH))
    days = max(0, days)
    excluded = DEFAULT_EXCLUDED_PREDICATES if exclude_predicate is None else exclude_predicate

    edges = _all_edges(excluded, days)
    degrees = _degrees(edges)
    nodes = _entity_nodes(entity_type, degrees) + _concept_nodes(namespace, degrees)

    if center is not None:
        keep = _neighbourhood(edges, center, depth)
        nodes = [node for node in nodes if node["id"] in keep]
        # The centre outranks everything else so a Top-N cut never removes the
        # one node the whole view is about.
        for node in nodes:
            if node["id"] == center:
                node["_rank"] = (float("inf"), 0)
    else:
        nodes = [node for node in nodes if node["value"] >= min_degree]

    if len(nodes) > limit:
        nodes.sort(key=lambda node: (-node["_rank"][0], -node["_rank"][1], node["name"]))
        if min_degree >= 1 or center is not None:
            nodes = _select_connected(nodes, edges, limit, center)
        else:
            # min_degree=0 is the explicit "show me everything that matched"
            # mode. Honouring that means a plain rank cut, isolated dots and all.
            nodes = nodes[:limit]
        logger.info("Graph truncated to %s nodes (limit=%s)", len(nodes), limit)
        truncated = True
    else:
        truncated = False

    for node in nodes:
        del node["_rank"]

    return {
        "nodes": nodes,
        "links": _links_between(edges, {node["id"] for node in nodes}),
        "categories": _categories(nodes),
        "truncated": truncated,
    }
