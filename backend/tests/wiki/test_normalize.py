"""Normalisation tests: the match key, the predicate table, alias merging."""

import pytest

from apps.wiki.services.normalize import (
    CANONICAL_PREDICATES,
    PREDICATE_ALIASES,
    merge_aliases,
    normalize_name,
    normalize_predicate,
)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("OpenAI", "openai"),
        ("Open  AI", "openai"),
        ("  GPT-5  ", "gpt5"),
        ("Open\tAI\nLabs", "openailabs"),
        ("混合专家模型", "混合专家模型"),
    ],
)
def test_normalize_name_folds_case_and_separators(given, expected):
    assert normalize_name(given) == expected


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # Every one of these sat in the live database as two separate rows.
        ("小米 18 Fold", "小米18 Fold"),
        ("约翰 · 特努斯", "约翰·特努斯"),
        ("蒂姆 · 库克", "蒂姆·库克"),
        ("DeepSeek V4 Flash", "DeepSeek-V4-Flash"),
        ("U-Net", "Unet"),
        ("agents.md", "AGENTS.md"),
        ("Open AI", "OpenAI"),
    ],
)
def test_surface_variants_of_one_name_share_a_key(left, right):
    assert normalize_name(left) == normalize_name(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("GPT-5", "GPT-4"),
        ("Llama 3.1", "Llama 3.2"),
        ("小米 18", "小米 17"),
    ],
)
def test_names_that_differ_in_substance_keep_different_keys(left, right):
    """Separators are noise; the characters around them are not."""
    assert normalize_name(left) != normalize_name(right)


def test_a_name_made_only_of_separators_does_not_collapse_to_nothing():
    """An empty key would collide with every other punctuation-only name."""
    assert normalize_name("---") != ""
    assert normalize_name("---") != normalize_name("...")


@pytest.mark.parametrize(("given", "expected"), [("推出", "发布"), ("发行", "发布"), ("上线", "发布")])
def test_synonyms_fold_onto_the_canonical_predicate(given, expected):
    assert normalize_predicate(given) == expected


def test_a_canonical_predicate_is_left_alone():
    for predicate in CANONICAL_PREDICATES:
        assert normalize_predicate(predicate) == predicate


def test_an_unmapped_predicate_survives_unchanged():
    # Better an unrecognised predicate than a wrong one.
    assert normalize_predicate("孵化") == "孵化"


def test_predicates_are_whitespace_normalised():
    assert normalize_predicate("  推出 ") == "发布"


def test_every_alias_points_at_a_canonical_predicate():
    unknown = {target for target in PREDICATE_ALIASES.values() if target not in CANONICAL_PREDICATES}

    assert unknown == set()


def test_no_alias_is_also_a_canonical_predicate():
    # A word that is both would make normalisation order-dependent.
    assert set(PREDICATE_ALIASES) & set(CANONICAL_PREDICATES) == set()


def test_the_table_covers_the_documented_verb_list():
    # PROMPTS.md offers the model 20 predicates; each should have somewhere to
    # collapse synonyms to, or the table is not doing its job.
    covered = set(PREDICATE_ALIASES.values())

    assert {"发布", "收购", "投资", "合作", "竞争", "采用"} <= covered


def test_merge_aliases_is_a_sorted_deduplicated_union():
    assert merge_aliases(["b", "a"], ["c", "a"]) == ["a", "b", "c"]


def test_merge_aliases_drops_blanks_and_trims():
    assert merge_aliases(["  Open AI  ", ""], ["   ", "OpenAI"]) == ["Open AI", "OpenAI"]


def test_merge_aliases_ignores_non_strings():
    assert merge_aliases(["ok"], [None, 7]) == ["ok"]


def test_merge_aliases_is_stable_across_runs():
    # Sorted output means a re-run over the same articles produces byte-identical
    # JSON instead of showing up as a change.
    assert merge_aliases(["b", "a"], []) == merge_aliases(["a", "b"], [])
