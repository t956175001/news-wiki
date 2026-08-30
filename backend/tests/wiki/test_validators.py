"""Validator tests: one case per row of the 「校验规则」 table in docs/PROMPTS.md.

The distinction under test throughout is raise-vs-skip. A `SchemaError` costs a
whole LLM call on retry, so anything that raises had better be a shape problem
the model can plausibly fix on a second attempt.
"""

import pytest

from apps.wiki.services.validators import (
    EVIDENCE_PENALTY,
    SchemaError,
    validate_concepts,
    validate_entities,
    validate_linkages,
)

ARTICLE_IDS = {42, 43}

ARTICLE_TEXT = "OpenAI 于本周正式发布 GPT-5，主打推理能力提升。业界普遍认为混合专家模型仍是主流路线。"
ARTICLE_TEXTS = {42: ARTICLE_TEXT}

KNOWN_ENTITIES = ["OpenAI", "GPT-5"]
KNOWN_CONCEPTS = ["混合专家模型"]


def entity(**overrides) -> dict:
    return {
        "name": "OpenAI",
        "type": "org",
        "aliases": ["Open AI"],
        "summary": "美国人工智能研究公司。",
        "confidence": 0.95,
        "evidence": "OpenAI 于本周正式发布 GPT-5",
        "raw_article_id": 42,
        **overrides,
    }


def concept(**overrides) -> dict:
    return {
        "name": "混合专家模型",
        "namespace": "technique",
        "definition": "把模型拆成多个专家子网络的架构路线。",
        "signals": ["混合专家"],
        "confidence": 0.9,
        "evidence": "业界普遍认为混合专家模型仍是主流路线",
        "raw_article_id": 42,
        **overrides,
    }


def linkage(**overrides) -> dict:
    return {
        "subject": "OpenAI",
        "predicate": "发布",
        "object_type": "entity",
        "object": "GPT-5",
        "confidence": 0.92,
        "evidence": "OpenAI 于本周正式发布 GPT-5",
        "raw_article_id": 42,
        **overrides,
    }


def entities(*items):
    return {"entities": list(items)}


def concepts(*items):
    return {"concepts": list(items)}


def linkages(*items):
    return {"linkages": list(items)}


def check_entities(payload, **kwargs):
    return validate_entities(payload, ARTICLE_IDS, **kwargs)


def check_concepts(payload, **kwargs):
    return validate_concepts(payload, ARTICLE_IDS, **kwargs)


def check_linkages(payload, **kwargs):
    return validate_linkages(payload, ARTICLE_IDS, KNOWN_ENTITIES, KNOWN_CONCEPTS, **kwargs)


# Uniform signatures, so the rules that apply to all three steps can be
# parametrized instead of copied.
ALL_VALIDATORS = [
    (check_entities, "entities"),
    (check_concepts, "concepts"),
    (check_linkages, "linkages"),
]


# --- happy path ---------------------------------------------------------


def test_a_valid_entity_survives_intact():
    items, stats = validate_entities(entities(entity()), ARTICLE_IDS, article_texts=ARTICLE_TEXTS)

    assert items == [
        {
            "name": "OpenAI",
            "type": "org",
            "aliases": ["Open AI"],
            "summary": "美国人工智能研究公司。",
            "confidence": 0.95,
            "evidence": "OpenAI 于本周正式发布 GPT-5",
            "raw_article_id": 42,
        }
    ]
    assert stats == {
        "skipped_invalid_article_ids": 0,
        "evidence_empty": 0,
        "evidence_not_in_source": 0,
        "coerced_types": 0,
    }


def test_a_valid_concept_survives_intact():
    items, stats = validate_concepts(concepts(concept()), ARTICLE_IDS, article_texts=ARTICLE_TEXTS)

    assert items[0]["name"] == "混合专家模型"
    assert items[0]["namespace"] == "technique"
    assert items[0]["signals"] == ["混合专家"]
    assert stats["evidence_not_in_source"] == 0


def test_a_valid_linkage_survives_intact():
    items, stats = check_linkages(linkages(linkage()), article_texts=ARTICLE_TEXTS)

    assert items == [
        {
            "subject": "OpenAI",
            "predicate": "发布",
            "object": "GPT-5",
            "object_type": "entity",
            "confidence": 0.92,
            "evidence": "OpenAI 于本周正式发布 GPT-5",
            "raw_article_id": 42,
        }
    ]
    assert sum(stats.values()) == 0


@pytest.mark.parametrize(("validate", "root_key"), ALL_VALIDATORS)
def test_an_empty_array_is_legal_and_does_not_retry(validate, root_key):
    # PROMPTS.md: "结果为空数组 | 合法，不重试"
    items, stats = validate({root_key: []})

    assert items == []
    assert sum(stats.values()) == 0


# --- shape errors: raise, so the pipeline retries the call --------------


@pytest.mark.parametrize(("validate", "root_key"), ALL_VALIDATORS)
def test_a_missing_root_key_raises(validate, root_key):
    with pytest.raises(SchemaError, match=f"Missing root key '{root_key}'"):
        validate({"something_else": []})


def test_a_non_array_root_raises():
    with pytest.raises(SchemaError, match="must be an array"):
        validate_entities({"entities": {"name": "OpenAI"}}, ARTICLE_IDS)


def test_a_non_object_payload_raises():
    with pytest.raises(SchemaError, match="top level"):
        validate_entities([entity()], ARTICLE_IDS)


def test_a_non_object_item_raises():
    with pytest.raises(SchemaError, match=r"entities\[1\] must be an object"):
        validate_entities(entities(entity(), "OpenAI"), ARTICLE_IDS)


@pytest.mark.parametrize("field", ["name", "type", "raw_article_id"])
def test_a_missing_required_entity_field_raises(field):
    broken = entity()
    del broken[field]

    with pytest.raises(SchemaError, match=f"missing required field '{field}'"):
        validate_entities(entities(broken), ARTICLE_IDS)


@pytest.mark.parametrize("field", ["name", "namespace", "raw_article_id"])
def test_a_missing_required_concept_field_raises(field):
    broken = concept()
    del broken[field]

    with pytest.raises(SchemaError, match=f"missing required field '{field}'"):
        validate_concepts(concepts(broken), ARTICLE_IDS)


@pytest.mark.parametrize("field", ["subject", "predicate", "object", "object_type", "raw_article_id"])
def test_a_missing_required_linkage_field_raises(field):
    broken = linkage()
    del broken[field]

    with pytest.raises(SchemaError, match=f"missing required field '{field}'"):
        check_linkages(linkages(broken))


def test_a_null_required_field_counts_as_missing():
    with pytest.raises(SchemaError, match="missing required field 'name'"):
        validate_entities(entities(entity(name=None)), ARTICLE_IDS)


def test_an_empty_name_raises():
    with pytest.raises(SchemaError, match="must not be empty"):
        validate_entities(entities(entity(name="   ")), ARTICLE_IDS)


def test_a_non_string_name_raises():
    with pytest.raises(SchemaError, match="must be a string"):
        validate_entities(entities(entity(name=123)), ARTICLE_IDS)


@pytest.mark.parametrize("value", ["abc", [], {}, float("nan"), float("inf")])
def test_a_non_numeric_confidence_raises(value):
    with pytest.raises(SchemaError):
        validate_entities(entities(entity(confidence=value)), ARTICLE_IDS)


def test_a_boolean_confidence_raises():
    # `isinstance(True, int)` would otherwise let this through as 1.0.
    with pytest.raises(SchemaError, match="got bool"):
        validate_entities(entities(entity(confidence=True)), ARTICLE_IDS)


def test_a_numeric_string_confidence_is_accepted():
    items, _ = validate_entities(entities(entity(confidence="0.42")), ARTICLE_IDS)

    assert items[0]["confidence"] == 0.42


@pytest.mark.parametrize(("given", "expected"), [(1.7, 1.0), (-0.5, 0.0), (0.5, 0.5)])
def test_confidence_is_clamped_to_the_unit_interval(given, expected):
    items, _ = validate_entities(entities(entity(confidence=given)), ARTICLE_IDS)

    assert items[0]["confidence"] == expected


def test_a_missing_confidence_defaults_to_full():
    broken = entity()
    del broken["confidence"]

    items, _ = validate_entities(entities(broken), ARTICLE_IDS)

    assert items[0]["confidence"] == 1.0


def test_non_list_aliases_raise():
    with pytest.raises(SchemaError, match="must be an array of strings"):
        validate_entities(entities(entity(aliases="Open AI")), ARTICLE_IDS)


def test_aliases_containing_a_non_string_raise():
    with pytest.raises(SchemaError, match="only strings"):
        validate_entities(entities(entity(aliases=["Open AI", 7])), ARTICLE_IDS)


def test_non_list_signals_raise():
    with pytest.raises(SchemaError, match="must be an array of strings"):
        validate_concepts(concepts(concept(signals="混合专家")), ARTICLE_IDS)


def test_missing_aliases_default_to_empty():
    broken = entity()
    del broken["aliases"]

    items, _ = validate_entities(entities(broken), ARTICLE_IDS)

    assert items[0]["aliases"] == []


# --- value errors: skip the item, count it, keep going ------------------


def test_an_article_id_outside_the_batch_is_skipped_and_counted():
    payload = entities(entity(), entity(name="Anthropic", raw_article_id=999))

    items, stats = validate_entities(payload, ARTICLE_IDS)

    assert [item["name"] for item in items] == ["OpenAI"]
    assert stats["skipped_invalid_article_ids"] == 1


def test_an_unparseable_article_id_is_skipped_and_counted():
    items, stats = validate_entities(entities(entity(raw_article_id="forty-two")), ARTICLE_IDS)

    assert items == []
    assert stats["skipped_invalid_article_ids"] == 1


def test_a_numeric_string_article_id_is_accepted():
    items, stats = validate_entities(entities(entity(raw_article_id="42")), ARTICLE_IDS)

    assert items[0]["raw_article_id"] == 42
    assert stats["skipped_invalid_article_ids"] == 0


def test_a_whole_number_float_article_id_is_accepted():
    items, stats = validate_entities(entities(entity(raw_article_id=42.0)), ARTICLE_IDS)

    # JSON has one number type, so a model that writes `42.0` still means 42.
    assert items[0]["raw_article_id"] == 42
    assert stats["skipped_invalid_article_ids"] == 0


@pytest.mark.parametrize(
    "value",
    [42.5, True, False, [42], {"id": 42}],
    ids=["fractional", "true", "false", "list", "object"],
)
def test_an_article_id_that_is_not_a_whole_number_is_skipped(value):
    """Skipped, not raised: whatever it is, it is not one of this batch's ids.

    `isinstance(True, int)` is True in Python, so booleans need the explicit
    check — otherwise `raw_article_id: true` would silently cite article 1.
    """
    items, stats = validate_entities(entities(entity(raw_article_id=value)), ARTICLE_IDS)

    assert items == []
    assert stats["skipped_invalid_article_ids"] == 1


def test_a_concept_citing_an_unknown_article_is_skipped():
    items, stats = validate_concepts(concepts(concept(raw_article_id=999)), ARTICLE_IDS)

    assert items == []
    assert stats["skipped_invalid_article_ids"] == 1


def test_a_linkage_citing_an_unknown_article_is_skipped():
    items, stats = check_linkages(linkages(linkage(raw_article_id=999)))

    assert items == []
    assert stats["skipped_invalid_article_ids"] == 1


# --- evidence -----------------------------------------------------------


def test_empty_evidence_keeps_the_item_but_is_counted():
    # PROMPTS.md: "evidence 为空 | 保留该项但不建 Evidence 记录"
    items, stats = validate_entities(entities(entity(evidence="")), ARTICLE_IDS, article_texts=ARTICLE_TEXTS)

    assert len(items) == 1
    assert items[0]["evidence"] == ""
    assert items[0]["confidence"] == 0.95
    assert stats["evidence_empty"] == 1
    assert stats["evidence_not_in_source"] == 0


def test_missing_evidence_is_treated_as_empty():
    broken = entity()
    del broken["evidence"]

    items, stats = validate_entities(entities(broken), ARTICLE_IDS, article_texts=ARTICLE_TEXTS)

    assert items[0]["evidence"] == ""
    assert stats["evidence_empty"] == 1


def test_evidence_that_is_not_in_the_source_is_discounted_not_dropped():
    items, stats = validate_entities(
        entities(entity(evidence="OpenAI 收购了一家芯片公司")),
        ARTICLE_IDS,
        article_texts=ARTICLE_TEXTS,
    )

    assert len(items) == 1
    assert items[0]["confidence"] == pytest.approx(0.95 * EVIDENCE_PENALTY)
    assert stats["evidence_not_in_source"] == 1


def test_whitespace_differences_do_not_count_as_invented_evidence():
    # The reason the comparison strips whitespace: models reflow quotes.
    items, stats = validate_entities(
        entities(entity(evidence="OpenAI  于本周\n正式发布   GPT-5")),
        ARTICLE_IDS,
        article_texts=ARTICLE_TEXTS,
    )

    assert items[0]["confidence"] == 0.95
    assert stats["evidence_not_in_source"] == 0


def test_evidence_is_not_checked_when_no_source_text_is_supplied():
    items, stats = validate_entities(entities(entity(evidence="完全编造的一句话")), ARTICLE_IDS)

    assert items[0]["confidence"] == 0.95
    assert stats["evidence_not_in_source"] == 0


def test_evidence_for_an_article_with_no_supplied_text_is_left_alone():
    items, stats = validate_entities(
        entities(entity(raw_article_id=43, evidence="不在 42 号文里的话")),
        ARTICLE_IDS,
        article_texts=ARTICLE_TEXTS,
    )

    assert items[0]["confidence"] == 0.95
    assert stats["evidence_not_in_source"] == 0


def test_discounted_confidence_applies_to_linkages_too():
    items, stats = check_linkages(
        linkages(linkage(evidence="OpenAI 与某公司达成合作")), article_texts=ARTICLE_TEXTS
    )

    assert items[0]["confidence"] == pytest.approx(0.92 * EVIDENCE_PENALTY)
    assert stats["evidence_not_in_source"] == 1


# --- enum coercion ------------------------------------------------------


def test_an_unknown_entity_type_becomes_other_and_is_counted():
    # Django does not enforce `choices` on save, so an unlisted type would reach
    # the DB and break the graph's category axis.
    items, stats = validate_entities(entities(entity(type="company")), ARTICLE_IDS)

    assert items[0]["type"] == "other"
    assert stats["coerced_types"] == 1


def test_a_known_entity_type_is_lowercased_without_being_counted():
    items, stats = validate_entities(entities(entity(type="ORG")), ARTICLE_IDS)

    assert items[0]["type"] == "org"
    assert stats["coerced_types"] == 0


def test_an_unknown_namespace_becomes_other_and_is_counted():
    items, stats = validate_concepts(concepts(concept(namespace="架构")), ARTICLE_IDS)

    assert items[0]["namespace"] == "other"
    assert stats["coerced_types"] == 1


# --- linkage reference resolution ---------------------------------------


def test_a_linkage_naming_an_unknown_subject_is_skipped_and_counted():
    items, stats = check_linkages(linkages(linkage(subject="DeepMind")))

    assert items == []
    assert stats["skipped_unknown_refs"] == 1


def test_a_linkage_naming_an_unknown_object_is_skipped_and_counted():
    items, stats = check_linkages(linkages(linkage(object="Gemini 3")))

    assert items == []
    assert stats["skipped_unknown_refs"] == 1


def test_good_linkages_survive_alongside_skipped_ones():
    items, stats = check_linkages(linkages(linkage(), linkage(object="Gemini 3")))

    assert len(items) == 1
    assert stats["skipped_unknown_refs"] == 1


def test_a_concept_object_resolves():
    items, stats = check_linkages(linkages(linkage(object="混合专家模型", object_type="concept")))

    assert items[0]["object_type"] == "concept"
    assert items[0]["object"] == "混合专家模型"
    assert stats["corrected_object_types"] == 0


def test_names_are_matched_on_case_and_spacing_not_bytes():
    items, _ = check_linkages(linkages(linkage(subject="openai", object="gpt-5")))

    # Resolved back to the canonical names so persistence can look them up.
    assert items[0]["subject"] == "OpenAI"
    assert items[0]["object"] == "GPT-5"


def test_a_mislabelled_object_type_is_corrected_from_the_name():
    items, stats = check_linkages(linkages(linkage(object="混合专家模型", object_type="entity")))

    assert items[0]["object_type"] == "concept"
    assert stats["corrected_object_types"] == 1


def test_a_garbage_object_type_still_resolves_by_name():
    items, stats = check_linkages(linkages(linkage(object_type="thing")))

    assert items[0]["object_type"] == "entity"
    assert stats["corrected_object_types"] == 1


def test_a_self_referential_linkage_is_skipped_and_counted():
    # Hard constraint 5 of the linkage prompt; a self-loop adds no edge and the
    # DB's uniqueness constraint would happily accept it.
    items, stats = check_linkages(linkages(linkage(object="OpenAI")))

    assert items == []
    assert stats["skipped_self_references"] == 1


def test_stats_keys_are_always_present_even_at_zero():
    _, stats = check_linkages(linkages())

    assert set(stats) == {
        "skipped_invalid_article_ids",
        "evidence_empty",
        "evidence_not_in_source",
        "skipped_unknown_refs",
        "skipped_self_references",
        "corrected_object_types",
    }
