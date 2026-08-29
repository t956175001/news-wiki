"""Wiki endpoints, and above all the entry detail response.

`docs/ARCHITECTURE.md` 4.1 is a contract with the frontend: the types in
`src/types/` are written against that exact JSON. So these tests assert on field
names and nesting, not just on status codes — a rename that keeps the endpoint
returning 200 is still a broken page.

The query-count test is the other half. The entry page is one request by design,
and a design like that fails silently: it keeps working, just slower, until an
entity with fifty relations makes it a hundred queries.
"""

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
    body = client.get("/api/v1/wiki/graph/?limit=1").json()

    assert body["truncated"] is True
    assert len(body["nodes"]) == 1
    # Ranked by mention_count, so the most-cited entity is the one that stays.
    assert body["nodes"][0]["name"] == "OpenAI"


def test_truncation_drops_edges_to_nodes_that_did_not_survive(client, entry):
    body = client.get("/api/v1/wiki/graph/?limit=1").json()

    assert body["links"] == []


def test_the_graph_can_be_filtered_by_entity_type(client, entry):
    body = client.get("/api/v1/wiki/graph/?entity_type=product").json()

    names = {node["name"] for node in body["nodes"]}
    assert "OpenAI" not in names
    assert "GPT-5" in names


def test_the_graph_can_be_filtered_by_namespace(client, entry):
    body = client.get("/api/v1/wiki/graph/?namespace=policy").json()

    assert "混合专家模型" not in {node["name"] for node in body["nodes"]}


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
