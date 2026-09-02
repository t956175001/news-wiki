"""Wiki endpoints, and above all the entry detail response.

`docs/ARCHITECTURE.md` 4.1 is a contract with the frontend: the types in
`src/types/` are written against that exact JSON. So these tests assert on field
names and nesting, not just on status codes — a rename that keeps the endpoint
returning 200 is still a broken page.

The query-count test is the other half. The entry page is one request by design,
and a design like that fails silently: it keeps working, just slower, until an
entity with fifty relations makes it a hundred queries.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ingest.models import RawArticle, RssSource
from apps.ops.models import ExtractionRun
from apps.wiki.models import Concept, Entity, Evidence, Linkage

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def entry():
    """One entity with an out-edge, an in-edge, and evidence on both."""
    source = RssSource.objects.create(name="机器之心", url="https://example.com/feed")
    article = RawArticle.objects.create(
        source=source,
        title="OpenAI 发布 GPT-5",
        url="https://example.com/gpt5",
        content="OpenAI 于本周正式发布 GPT-5，主打推理能力提升。",
        content_hash="view-hash-0001",
        publish_time=timezone.now(),
    )
    run = ExtractionRun.objects.create(run_id="a" * 32, trigger="cron", status="success")

    openai = Entity.objects.create(
        name="OpenAI",
        normalized_name="openai",
        entity_type="org",
        aliases=["Open AI"],
        summary="美国人工智能研究公司。",
        confidence=0.95,
        mention_count=17,
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )
    gpt5 = Entity.objects.create(
        name="GPT-5", normalized_name="gpt-5", entity_type="product", mention_count=9
    )
    moe = Concept.objects.create(name="混合专家模型", namespace="technique")

    out_edge = Linkage.objects.create(
        subject_entity=openai, predicate="发布", object_entity=gpt5, confidence=0.92
    )
    concept_edge = Linkage.objects.create(
        subject_entity=openai, predicate="采用", object_concept=moe, confidence=0.7
    )
    in_edge = Linkage.objects.create(
        subject_entity=gpt5, predicate="属于", object_entity=openai, confidence=0.8
    )

    for linkage in (out_edge, concept_edge, in_edge):
        Evidence.objects.create(
            raw_article=article,
            linkage=linkage,
            snippet="OpenAI 于本周正式发布 GPT-5，主打推理能力提升。",
            extraction_run=run,
            prompt_key="wiki.extract_linkages",
            prompt_version=2,
        )

    return {
        "openai": openai,
        "gpt5": gpt5,
        "concept": moe,
        "article": article,
        "run": run,
        "out_edge": out_edge,
        "in_edge": in_edge,
        "concept_edge": concept_edge,
    }


def entity_detail(client, entity) -> dict:
    response = client.get(f"/api/v1/wiki/entities/{entity.pk}/")
    assert response.status_code == 200
    return response.json()


# --- entry detail: the section 4.1 contract -----------------------------


def test_the_entity_header_matches_the_contract(client, entry):
    body = entity_detail(client, entry["openai"])

    assert body["id"] == entry["openai"].pk
    assert body["name"] == "OpenAI"
    assert body["entity_type"] == "org"
    assert body["entity_type_display"] == "Organization"
    assert body["aliases"] == ["Open AI"]
    assert body["confidence"] == 0.95
    assert body["mention_count"] == 17
    assert body["first_seen_at"] is not None
    assert body["last_seen_at"] is not None


def test_outgoing_and_incoming_edges_share_one_array(client, entry):
    body = entity_detail(client, entry["openai"])

    directions = sorted(linkage["direction"] for linkage in body["linkages"])
    assert directions == ["in", "out", "out"]


def test_an_out_edge_points_at_the_object(client, entry):
    body = entity_detail(client, entry["openai"])
    out_edge = next(item for item in body["linkages"] if item["id"] == entry["out_edge"].pk)

    assert out_edge["direction"] == "out"
    assert out_edge["predicate"] == "发布"
    assert out_edge["confidence"] == 0.92
    assert out_edge["object"] == {
        "kind": "entity",
        "id": entry["gpt5"].pk,
        "name": "GPT-5",
        "entity_type": "product",
    }


def test_an_in_edge_points_at_the_subject(client, entry):
    body = entity_detail(client, entry["openai"])
    in_edge = next(item for item in body["linkages"] if item["id"] == entry["in_edge"].pk)

    # `object` is the *other* end of the edge, so the page can render
    # "GPT-5 -[属于]-> OpenAI" without a second lookup.
    assert in_edge["direction"] == "in"
    assert in_edge["object"]["id"] == entry["gpt5"].pk
    assert in_edge["object"]["name"] == "GPT-5"


def test_a_concept_object_carries_its_namespace(client, entry):
    body = entity_detail(client, entry["openai"])
    edge = next(item for item in body["linkages"] if item["id"] == entry["concept_edge"].pk)

    assert edge["object"] == {
        "kind": "concept",
        "id": entry["concept"].pk,
        "name": "混合专家模型",
        "namespace": "technique",
    }


def test_every_evidence_field_the_entry_page_needs_is_present(client, entry):
    body = entity_detail(client, entry["openai"])
    evidence = body["linkages"][0]["evidences"][0]

    assert evidence["snippet"].startswith("OpenAI")
    assert evidence["prompt_key"] == "wiki.extract_linkages"
    assert evidence["prompt_version"] == 2
    assert evidence["run_id"] == entry["run"].run_id
    assert evidence["article"] == {
        "id": entry["article"].pk,
        "title": "OpenAI 发布 GPT-5",
        "url": "https://example.com/gpt5",
        "publish_time": entry["article"].publish_time.astimezone().isoformat(),
        "source_name": "机器之心",
    }


def test_no_evidence_field_comes_back_null(client, entry):
    body = entity_detail(client, entry["openai"])

    for linkage in body["linkages"]:
        for evidence in linkage["evidences"]:
            assert all(value is not None for value in evidence.values())
            assert all(value is not None for value in evidence["article"].values())


def test_linkages_are_grouped_by_predicate(client, entry):
    body = entity_detail(client, entry["openai"])

    predicates = [linkage["predicate"] for linkage in body["linkages"]]
    assert predicates == sorted(predicates)


def test_an_entity_with_no_relations_returns_an_empty_array(client):
    lonely = Entity.objects.create(name="孤儿", normalized_name="孤儿", entity_type="other")

    body = entity_detail(client, lonely)

    assert body["linkages"] == []


def test_a_missing_entity_uses_the_error_envelope(client):
    response = client.get("/api/v1/wiki/entities/999999/")

    assert response.status_code == 404
    assert set(response.json()) == {"code", "detail"}


# --- the N+1 guard ------------------------------------------------------


def test_the_entry_page_costs_a_fixed_number_of_queries(client, entry, django_assert_num_queries):
    # entity + out-edges + their evidence + in-edges + their evidence.
    with django_assert_num_queries(5):
        client.get(f"/api/v1/wiki/entities/{entry['openai'].pk}/")


def test_more_relations_do_not_cost_more_queries(client, entry, django_assert_num_queries):
    """The point of the prefetching: cost is flat in the number of relations."""
    openai = entry["openai"]
    run = entry["run"]
    article = entry["article"]
    for index in range(20):
        other = Entity.objects.create(name=f"实体{index}", normalized_name=f"实体{index}", entity_type="org")
        linkage = Linkage.objects.create(subject_entity=openai, predicate="合作", object_entity=other)
        Evidence.objects.create(
            raw_article=article,
            linkage=linkage,
            snippet="片段",
            extraction_run=run,
            prompt_key="wiki.extract_linkages",
            prompt_version=2,
        )

    with django_assert_num_queries(5):
        response = client.get(f"/api/v1/wiki/entities/{openai.pk}/")

    assert len(response.json()["linkages"]) == 23


# --- entity list --------------------------------------------------------


def test_the_list_is_paginated_in_the_documented_shape(client, entry):
    body = client.get("/api/v1/wiki/entities/").json()

    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 2


def test_the_list_is_ordered_by_mention_count(client, entry):
    names = [item["name"] for item in client.get("/api/v1/wiki/entities/").json()["results"]]

    assert names == ["OpenAI", "GPT-5"]


def test_the_list_can_be_filtered_by_type(client, entry):
    body = client.get("/api/v1/wiki/entities/?entity_type=product").json()

    assert [item["name"] for item in body["results"]] == ["GPT-5"]


def test_search_matches_the_name(client, entry):
    body = client.get("/api/v1/wiki/entities/?search=gpt").json()

    assert [item["name"] for item in body["results"]] == ["GPT-5"]


def test_search_matches_an_alias(client, entry):
    """ "Open AI" is only stored in the aliases JSON, never in `name`."""
    body = client.get("/api/v1/wiki/entities/?search=Open AI").json()

    assert [item["name"] for item in body["results"]] == ["OpenAI"]


def test_the_list_does_not_carry_linkages(client, entry):
    first = client.get("/api/v1/wiki/entities/").json()["results"][0]

    assert "linkages" not in first


# --- concepts -----------------------------------------------------------


def test_concepts_list_and_filter(client, entry):
    assert client.get("/api/v1/wiki/concepts/").json()["count"] == 1
    assert client.get("/api/v1/wiki/concepts/?namespace=policy").json()["count"] == 0
    assert client.get("/api/v1/wiki/concepts/?search=混合").json()["count"] == 1


def test_a_concept_detail_carries_its_incoming_edges(client, entry):
    body = client.get(f"/api/v1/wiki/concepts/{entry['concept'].pk}/").json()

    assert body["namespace"] == "technique"
    assert len(body["linkages"]) == 1
    edge = body["linkages"][0]
    assert edge["direction"] == "in"
    assert edge["object"]["name"] == "OpenAI"
    assert edge["evidences"][0]["prompt_version"] == 2


# --- graph --------------------------------------------------------------


def test_the_graph_matches_the_echarts_shape(client, entry):
    body = client.get("/api/v1/wiki/graph/").json()

    assert set(body) == {"nodes", "links", "categories", "truncated"}
    assert body["truncated"] is False

    openai_node = next(node for node in body["nodes"] if node["name"] == "OpenAI")
    assert openai_node["id"] == f"e{entry['openai'].pk}"
    assert openai_node["category"] == "org"
    assert openai_node["value"] == 3  # two out-edges, one in-edge
    assert openai_node["symbolSize"] == 18  # 12 + 3 * 2


def test_concept_nodes_use_the_c_prefix(client, entry):
    body = client.get("/api/v1/wiki/graph/").json()

    concept_node = next(node for node in body["nodes"] if node["name"] == "混合专家模型")
    assert concept_node["id"] == f"c{entry['concept'].pk}"
    assert concept_node["category"] == "technique"


def test_links_reference_nodes_by_prefixed_id(client, entry):
    body = client.get("/api/v1/wiki/graph/").json()

    node_ids = {node["id"] for node in body["nodes"]}
    assert len(body["links"]) == 3
    for link in body["links"]:
        assert link["source"] in node_ids
        assert link["target"] in node_ids
        assert link["predicate"]
        assert 0 <= link["value"] <= 1


def test_symbol_size_is_capped(client):
    hub = Entity.objects.create(name="枢纽", normalized_name="枢纽", entity_type="org")
    for index in range(40):
        other = Entity.objects.create(name=f"n{index}", normalized_name=f"n{index}", entity_type="org")
        Linkage.objects.create(subject_entity=hub, predicate="关联", object_entity=other)

    body = client.get("/api/v1/wiki/graph/").json()
    hub_node = next(node for node in body["nodes"] if node["name"] == "枢纽")

    assert hub_node["value"] == 40
    assert hub_node["symbolSize"] == 60  # min(60, 12 + 80)


def test_the_graph_truncates_to_the_top_n(client, entry):
    """limit=1 cannot hold an edge, so this falls back to the plain rank cut."""
    body = client.get("/api/v1/wiki/graph/?limit=1").json()

    assert body["truncated"] is True
    assert len(body["nodes"]) == 1
    # Ranked by degree, so the best-connected node is the one that stays.
    assert body["nodes"][0]["name"] == "OpenAI"


def test_a_filter_that_isolates_everything_still_shows_the_nodes(client, entry):
    """`?entity_type=product` keeps GPT-5, whose relations all point at orgs.

    Every candidate is render-isolated, so edge-driven selection finds nothing
    to admit. An empty canvas would read as "no such data"; the nodes exist and
    should be shown.
    """
    for index in range(3):
        product = Entity.objects.create(
            name=f"产品{index}", normalized_name=f"产品{index}", entity_type="product"
        )
        Linkage.objects.create(subject_entity=entry["openai"], predicate="发布", object_entity=product)

    body = client.get("/api/v1/wiki/graph/?entity_type=product&limit=2").json()

    assert body["truncated"] is True
    assert len(body["nodes"]) == 2
    assert body["links"] == []


def test_truncation_drops_edges_to_nodes_that_did_not_survive(client, entry):
    body = client.get("/api/v1/wiki/graph/?limit=1").json()

    assert body["links"] == []


def test_truncation_never_leaves_a_node_without_a_visible_edge(client):
    """ADR-015, the second half.

    Ranking by degree is not enough on its own: a hub's neighbours are leaves,
    the leaves fall below the cut, and the hub lands on the canvas with nothing
    attached. Here two hubs of 6 leaves each compete for a 6-node budget — the
    right answer is one whole star, not both hub nodes plus four orphans.
    """
    for hub_index in range(2):
        hub = Entity.objects.create(
            name=f"枢纽{hub_index}", normalized_name=f"枢纽{hub_index}", entity_type="org"
        )
        for leaf_index in range(6):
            leaf = Entity.objects.create(
                name=f"叶{hub_index}-{leaf_index}",
                normalized_name=f"叶{hub_index}-{leaf_index}",
                entity_type="product",
            )
            Linkage.objects.create(subject_entity=hub, predicate="关联", object_entity=leaf)

    body = client.get("/api/v1/wiki/graph/?limit=6").json()

    assert body["truncated"] is True
    assert len(body["nodes"]) == 6
    drawn = {node_id for link in body["links"] for node_id in (link["source"], link["target"])}
    assert drawn == {node["id"] for node in body["nodes"]}


def test_min_degree_zero_keeps_the_plain_rank_cut(client):
    """The escape hatch has to stay honest: asked for everything, get everything.

    Ranked purely by degree, so the isolated node is last and gets cut — but it
    is eligible, which is the difference from the default view where it is not.
    """
    hub = Entity.objects.create(name="枢纽", normalized_name="枢纽", entity_type="org")
    leaf = Entity.objects.create(name="叶", normalized_name="叶", entity_type="product")
    Linkage.objects.create(subject_entity=hub, predicate="关联", object_entity=leaf)
    Entity.objects.create(name="孤点", normalized_name="孤点", entity_type="org")

    body = client.get("/api/v1/wiki/graph/?limit=3&min_degree=0").json()

    assert {node["name"] for node in body["nodes"]} == {"枢纽", "叶", "孤点"}
    assert body["truncated"] is False


def test_truncation_keeps_the_best_connected_node_not_the_most_mentioned(client):
    """ADR-015. The reason the live graph was 150 nodes and 37 edges.

    `mention_count` is 1 for almost every entity, so ranking by it made the cut
    arbitrary and routinely dropped the hubs. Here the hub is mentioned once and
    the loner seventeen times: the hub is the one worth drawing.
    """
    hub = Entity.objects.create(name="枢纽", normalized_name="枢纽", entity_type="org", mention_count=1)
    for index in range(3):
        other = Entity.objects.create(
            name=f"n{index}", normalized_name=f"n{index}", entity_type="product", mention_count=1
        )
        Linkage.objects.create(subject_entity=hub, predicate="关联", object_entity=other)
    Entity.objects.create(name="独行侠", normalized_name="独行侠", entity_type="org", mention_count=17)

    body = client.get("/api/v1/wiki/graph/?limit=1&min_degree=0").json()

    assert [node["name"] for node in body["nodes"]] == ["枢纽"]


# --- min_degree ---------------------------------------------------------


def test_isolated_nodes_are_hidden_by_default(client, entry):
    Entity.objects.create(name="没有关系的实体", normalized_name="没有关系的实体", entity_type="org")

    names = {node["name"] for node in client.get("/api/v1/wiki/graph/").json()["nodes"]}

    assert "没有关系的实体" not in names
    assert "OpenAI" in names


def test_min_degree_zero_brings_the_isolated_nodes_back(client, entry):
    Entity.objects.create(name="没有关系的实体", normalized_name="没有关系的实体", entity_type="org")

    body = client.get("/api/v1/wiki/graph/?min_degree=0").json()

    assert "没有关系的实体" in {node["name"] for node in body["nodes"]}


def test_min_degree_can_be_raised_to_show_only_hubs(client, entry):
    body = client.get("/api/v1/wiki/graph/?min_degree=3").json()

    # OpenAI has three edges; GPT-5 has two and the concept has one.
    assert [node["name"] for node in body["nodes"]] == ["OpenAI"]
    # Its edges all point at nodes that were cut, so none can be drawn.
    assert body["links"] == []


# --- predicate filtering ------------------------------------------------


def _vague_edge(entry):
    """An edge labelled `涉及` — the predicate that says almost nothing."""
    other = Entity.objects.create(name="某场会议", normalized_name="某场会议", entity_type="event")
    return Linkage.objects.create(subject_entity=entry["openai"], predicate="涉及", object_entity=other)


def test_the_vaguest_predicate_is_hidden_by_default(client, entry):
    """ADR-019. `涉及` was 17% of the edges on the live graph and carries no
    relation of its own — two nodes being "involved" is the absence of a fact."""
    _vague_edge(entry)

    body = client.get("/api/v1/wiki/graph/").json()

    assert "涉及" not in {link["predicate"] for link in body["links"]}
    assert "某场会议" not in {node["name"] for node in body["nodes"]}


def test_an_empty_exclusion_brings_every_predicate_back(client, entry):
    """Present-but-empty differs from absent: it means "exclude nothing"."""
    _vague_edge(entry)

    body = client.get("/api/v1/wiki/graph/?exclude_predicate=").json()

    assert "涉及" in {link["predicate"] for link in body["links"]}


def test_predicates_can_be_excluded_by_name(client, entry):
    body = client.get("/api/v1/wiki/graph/?exclude_predicate=发布,采用").json()

    assert {link["predicate"] for link in body["links"]} == {"属于"}


def test_degree_counts_only_the_edges_that_survive_the_filters(client, entry):
    """`value` drives node size and the Top-N cut, so it has to describe the
    graph being drawn rather than the one sitting in the database."""
    before = {node["name"]: node["value"] for node in client.get("/api/v1/wiki/graph/").json()["nodes"]}
    after = {
        node["name"]: node["value"]
        for node in client.get("/api/v1/wiki/graph/?exclude_predicate=发布").json()["nodes"]
    }

    assert before["GPT-5"] == 2  # 发布 inbound, 属于 outbound
    assert after["GPT-5"] == 1


def test_a_node_left_with_no_visible_edge_drops_off_the_canvas(client, entry):
    """The concept hangs off a single 采用 edge; hide it and the node is a dot."""
    names = {
        node["name"] for node in client.get("/api/v1/wiki/graph/?exclude_predicate=采用").json()["nodes"]
    }

    assert "混合专家模型" not in names


# --- time window --------------------------------------------------------


def _dated_edge(entry, *, days_ago: int):
    """A relation whose only evidence comes from an article that old."""
    article = RawArticle.objects.create(
        source=entry["article"].source,
        title=f"{days_ago} 天前的报道",
        url=f"https://example.com/old-{days_ago}",
        content="旧闻。",
        content_hash=f"aged-hash-{days_ago}",
        publish_time=timezone.now() - timedelta(days=days_ago),
    )
    old = Entity.objects.create(
        name=f"旧实体{days_ago}", normalized_name=f"旧实体{days_ago}", entity_type="org"
    )
    linkage = Linkage.objects.create(subject_entity=entry["openai"], predicate="合作", object_entity=old)
    Evidence.objects.create(
        raw_article=article,
        linkage=linkage,
        snippet="旧闻。",
        extraction_run=entry["run"],
        prompt_key="wiki.extract_linkages",
        prompt_version=1,
    )
    return linkage, article


def test_relations_from_older_news_fall_out_of_the_window(client, entry):
    """ADR-019. The graph is cumulative; without a window it only ever grows,
    and what you see converges on the same all-time hubs."""
    _dated_edge(entry, days_ago=90)

    names = {node["name"] for node in client.get("/api/v1/wiki/graph/?days=30").json()["nodes"]}

    assert "旧实体90" not in names
    assert "GPT-5" in names  # the fixture's own article is dated today


def test_days_zero_means_the_whole_history(client, entry):
    _dated_edge(entry, days_ago=90)

    names = {node["name"] for node in client.get("/api/v1/wiki/graph/?days=0").json()["nodes"]}

    assert "旧实体90" in names


def test_the_window_reads_the_article_date_not_the_extraction_date(client, entry):
    """Extraction happens whenever the backlog gets to an article, so
    `Linkage.created_at` would report a two-month-old story as today's news."""
    linkage, _article = _dated_edge(entry, days_ago=90)

    assert (timezone.now() - linkage.created_at).days == 0  # created just now
    names = {node["name"] for node in client.get("/api/v1/wiki/graph/?days=30").json()["nodes"]}
    assert "旧实体90" not in names


def test_one_recent_source_keeps_a_relation_in_the_window(client, entry):
    """A relation is current if *any* article still supports it."""
    linkage, _old = _dated_edge(entry, days_ago=90)
    fresh = RawArticle.objects.create(
        source=entry["article"].source,
        title="今天又报了一次",
        url="https://example.com/fresh",
        content="新闻。",
        content_hash="fresh-hash-1",
        publish_time=timezone.now(),
    )
    Evidence.objects.create(
        raw_article=fresh,
        linkage=linkage,
        snippet="新闻。",
        extraction_run=entry["run"],
        prompt_key="wiki.extract_linkages",
        prompt_version=1,
    )

    names = {node["name"] for node in client.get("/api/v1/wiki/graph/?days=30").json()["nodes"]}

    assert "旧实体90" in names


def test_a_relation_whose_age_is_unknown_survives_the_window(client, entry):
    """The window retires old news; it does not hide what it cannot date.

    Two cases land here: a relation with no evidence at all, and evidence on an
    article whose feed gave no parseable date. Dropping either would mean the
    default view silently omits rows for a reason the reader cannot see.
    """
    undated_article = RawArticle.objects.create(
        source=entry["article"].source,
        title="没有日期的报道",
        url="https://example.com/undated",
        content="无日期。",
        content_hash="undated-hash-1",
        publish_time=None,
    )
    partner = Entity.objects.create(name="无日期实体", normalized_name="无日期实体", entity_type="org")
    linkage = Linkage.objects.create(subject_entity=entry["openai"], predicate="投资", object_entity=partner)
    Evidence.objects.create(
        raw_article=undated_article,
        linkage=linkage,
        snippet="无日期。",
        extraction_run=entry["run"],
        prompt_key="wiki.extract_linkages",
        prompt_version=1,
    )

    names = {node["name"] for node in client.get("/api/v1/wiki/graph/?days=30").json()["nodes"]}

    assert "无日期实体" in names


def test_the_window_does_not_double_count_degree(client, entry):
    """The evidence join can multiply rows; an edge backed by three articles is
    still one edge, and one relation for the node it hangs off."""
    linkage, _old = _dated_edge(entry, days_ago=1)
    for index in range(2):
        extra = RawArticle.objects.create(
            source=entry["article"].source,
            title=f"追加报道 {index}",
            url=f"https://example.com/extra-{index}",
            content="新闻。",
            content_hash=f"extra-hash-{index}",
            publish_time=timezone.now(),
        )
        Evidence.objects.create(
            raw_article=extra,
            linkage=linkage,
            snippet="新闻。",
            extraction_run=entry["run"],
            prompt_key="wiki.extract_linkages",
            prompt_version=1,
        )

    body = client.get("/api/v1/wiki/graph/?days=30").json()

    assert len([link for link in body["links"] if link["predicate"] == "合作"]) == 1
    assert next(node for node in body["nodes"] if node["name"] == "旧实体1")["value"] == 1


# --- ego graph ----------------------------------------------------------


def test_center_returns_only_the_neighbourhood(client, entry):
    outsider = Entity.objects.create(name="局外人", normalized_name="局外人", entity_type="org")
    Linkage.objects.create(subject_entity=outsider, predicate="关联", object_entity=outsider)

    body = client.get(f"/api/v1/wiki/graph/?center=e{entry['openai'].pk}").json()

    names = {node["name"] for node in body["nodes"]}
    assert names == {"OpenAI", "GPT-5", "混合专家模型"}
    assert "局外人" not in names


def test_the_neighbourhood_follows_edges_in_both_directions(client, entry):
    """`GPT-5 -[属于]-> OpenAI` belongs on OpenAI's page as much as the reverse."""
    body = client.get(f"/api/v1/wiki/graph/?center=e{entry['gpt5'].pk}&depth=1").json()

    assert "OpenAI" in {node["name"] for node in body["nodes"]}


def test_depth_two_reaches_one_hop_further(client, entry):
    far = Entity.objects.create(name="远端", normalized_name="远端", entity_type="product")
    Linkage.objects.create(subject_entity=entry["gpt5"], predicate="衍生", object_entity=far)

    one_hop = client.get(f"/api/v1/wiki/graph/?center=e{entry['openai'].pk}&depth=1").json()
    two_hops = client.get(f"/api/v1/wiki/graph/?center=e{entry['openai'].pk}&depth=2").json()

    assert "远端" not in {node["name"] for node in one_hop["nodes"]}
    assert "远端" in {node["name"] for node in two_hops["nodes"]}


def test_an_unknown_center_yields_an_empty_graph_rather_than_an_error(client, entry):
    response = client.get("/api/v1/wiki/graph/?center=e999999")

    assert response.status_code == 200
    assert response.json()["nodes"] == []


def test_a_center_with_no_relations_still_shows_itself(client, entry):
    """min_degree must not remove the one node the caller asked for by name."""
    lonely = Entity.objects.create(name="孤零零", normalized_name="孤零零", entity_type="org")

    body = client.get(f"/api/v1/wiki/graph/?center=e{lonely.pk}").json()

    assert [node["name"] for node in body["nodes"]] == ["孤零零"]
    assert body["links"] == []


def test_a_concept_can_be_the_center(client, entry):
    body = client.get(f"/api/v1/wiki/graph/?center=c{entry['concept'].pk}").json()

    assert {node["name"] for node in body["nodes"]} == {"混合专家模型", "OpenAI"}


def test_depth_is_capped(client, entry):
    """A depth of 99 on a connected graph would just be the whole graph."""
    capped = client.get(f"/api/v1/wiki/graph/?center=e{entry['openai'].pk}&depth=99").json()
    at_max = client.get(f"/api/v1/wiki/graph/?center=e{entry['openai'].pk}&depth=3").json()

    assert capped["nodes"] == at_max["nodes"]


def test_the_graph_can_be_filtered_by_entity_type(client, entry):
    body = client.get("/api/v1/wiki/graph/?entity_type=product").json()

    names = {node["name"] for node in body["nodes"]}
    assert "OpenAI" not in names
    assert "GPT-5" in names


def test_the_graph_can_be_filtered_by_namespace(client, entry):
    body = client.get("/api/v1/wiki/graph/?namespace=policy").json()

    assert "混合专家模型" not in {node["name"] for node in body["nodes"]}


def test_the_graph_can_be_filtered_by_multiple_entity_types(client, entry):
    body = client.get("/api/v1/wiki/graph/?entity_type=org,product").json()

    names = {node["name"] for node in body["nodes"]}
    assert "OpenAI" in names
    assert "GPT-5" in names


def test_the_graph_can_be_filtered_by_multiple_namespaces(client):
    subject = Entity.objects.create(name="主语", normalized_name="主语", entity_type="org")
    for name, namespace in (("A", "technique"), ("B", "policy"), ("C", "trend")):
        concept = Concept.objects.create(name=name, namespace=namespace)
        # Each needs an edge to survive the default min_degree=1.
        Linkage.objects.create(subject_entity=subject, predicate="采用", object_concept=concept)

    body = client.get("/api/v1/wiki/graph/?namespace=technique,policy").json()
    body["nodes"] = [node for node in body["nodes"] if node["id"].startswith("c")]

    names = {node["name"] for node in body["nodes"]}
    assert names == {"A", "B"}


def test_categories_are_listed_in_a_stable_order(client, entry):
    first = client.get("/api/v1/wiki/graph/").json()["categories"]
    second = client.get("/api/v1/wiki/graph/").json()["categories"]

    assert first == second
    # Model choice order, so ECharts gives a category the same colour every load.
    assert [category["name"] for category in first] == ["org", "product", "technique"]


def test_a_non_numeric_limit_uses_the_error_envelope(client, entry):
    response = client.get("/api/v1/wiki/graph/?limit=abc")

    assert response.status_code == 400
    assert response.json()["code"] == "PARSE_ERROR"


def test_an_empty_graph_is_not_an_error(client):
    body = client.get("/api/v1/wiki/graph/").json()

    assert body == {"nodes": [], "links": [], "categories": [], "truncated": False}
