"""Merging duplicate entity rows (ADR-019).

The thing under test is not "did the rows collapse" but "did anything get lost".
Every relation and every citation that pointed at a duplicate has to end up
pointing at the survivor, because a dropped citation is the one failure this
project cannot absorb.
"""

import pytest
from django.utils import timezone

from apps.ingest.models import RawArticle, RssSource
from apps.ops.models import ExtractionRun
from apps.wiki.models import Concept, Entity, Evidence, Linkage
from apps.wiki.services.merge import choose_primary, merge_duplicate_entities, merge_entities
from apps.wiki.services.normalize import normalize_name

pytestmark = pytest.mark.django_db

MODELS = {"entity_model": Entity, "linkage_model": Linkage, "evidence_model": Evidence}


@pytest.fixture
def article():
    source = RssSource.objects.create(name="测试源", url="https://example.com/feed")
    return RawArticle.objects.create(
        source=source,
        title="标题",
        url="https://example.com/a",
        content="正文",
        content_hash="merge-hash-0001",
        publish_time=timezone.now(),
    )


@pytest.fixture
def run():
    return ExtractionRun.objects.create(run_id="m" * 32, trigger="cron", status="success")


def make_entity(name, entity_type, *, key=None, **kwargs):
    """`key` writes the pre-migration `normalized_name` directly.

    Needed because the post-migration constraint forbids the very state these
    tests are about: two rows sharing a normalised name. The rows are therefore
    inserted under the keys they *had* before the re-keying, which is also what
    the migration finds when it runs.
    """
    return Entity.objects.create(
        name=name,
        normalized_name=key if key is not None else normalize_name(name),
        entity_type=entity_type,
        **kwargs,
    )


def evidence_for(article, run, **target):
    return Evidence.objects.create(
        raw_article=article,
        snippet="片段",
        extraction_run=run,
        prompt_key="wiki.extract_entities",
        prompt_version=1,
        **target,
    )


def test_the_survivor_is_the_most_mentioned_row():
    small = make_entity("GitHub", "org", key="github~org", mention_count=1)
    big = make_entity("GitHub", "product", key="github", mention_count=5)

    assert choose_primary([small, big], Linkage).pk == big.pk


def test_a_tie_on_mentions_is_broken_by_how_connected_the_row_is(article, run):
    quiet = make_entity("Twitter", "product", key="twitter", mention_count=2)
    linked = make_entity("Twitter", "org", key="twitter~org", mention_count=2)
    other = make_entity("Meta", "org")
    Linkage.objects.create(subject_entity=linked, predicate="合作", object_entity=other)

    assert choose_primary([quiet, linked], Linkage).pk == linked.pk


def test_every_citation_follows_the_entity_it_described(article, run):
    primary = make_entity("Hugging Face", "org", key="hugging face", mention_count=4)
    duplicate = make_entity("Hugging Face", "product", key="huggingface", mention_count=3)
    evidence_for(article, run, entity=duplicate)

    merge_entities(primary, [duplicate], **MODELS)

    assert Evidence.objects.filter(entity=primary).count() == 1
    assert not Entity.objects.filter(pk=duplicate.pk).exists()


def test_relations_on_both_sides_move_across(article, run):
    primary = make_entity("DeepSeek", "org", key="deepseek", mention_count=3)
    duplicate = make_entity("DeepSeek", "model", key="deepseek~model", mention_count=1)
    partner = make_entity("清华大学", "org")
    concept = Concept.objects.create(name="强化学习", namespace="technique")
    Linkage.objects.create(subject_entity=duplicate, predicate="采用", object_concept=concept)
    Linkage.objects.create(subject_entity=partner, predicate="合作", object_entity=duplicate)

    merge_entities(primary, [duplicate], **MODELS)

    assert Linkage.objects.filter(subject_entity=primary, object_concept=concept).exists()
    assert Linkage.objects.filter(subject_entity=partner, object_entity=primary).exists()
    assert Linkage.objects.count() == 2


def test_an_edge_between_the_two_rows_becomes_a_self_loop_and_is_dropped(article, run):
    """ "GitHub the org 属于 GitHub the product" is a statement about one thing."""
    primary = make_entity("GitHub", "product", key="github", mention_count=5)
    duplicate = make_entity("GitHub", "org", key="github~org", mention_count=1)
    loop = Linkage.objects.create(subject_entity=duplicate, predicate="属于", object_entity=primary)
    evidence_for(article, run, linkage=loop)

    merge_entities(primary, [duplicate], **MODELS)

    assert Linkage.objects.count() == 0
    assert Evidence.objects.count() == 0


def test_two_edges_that_collide_after_the_merge_keep_one_row_and_all_evidence(article, run):
    """`uniq_linkage_triple` forbids the duplicate, so the citations move instead."""
    primary = make_entity("Claude", "product", key="claude", mention_count=5)
    duplicate = make_entity("Claude", "model", key="claude~model", mention_count=1)
    anthropic = make_entity("Anthropic", "org")
    kept = Linkage.objects.create(
        subject_entity=primary, predicate="属于", object_entity=anthropic, confidence=0.6
    )
    doomed = Linkage.objects.create(
        subject_entity=duplicate, predicate="属于", object_entity=anthropic, confidence=0.9
    )
    evidence_for(article, run, linkage=kept)
    evidence_for(article, run, linkage=doomed)

    merge_entities(primary, [duplicate], **MODELS)

    assert Linkage.objects.count() == 1
    assert Evidence.objects.filter(linkage=kept).count() == 2
    kept.refresh_from_db()
    assert kept.confidence == 0.9  # corroboration only raises it


def test_the_losing_spelling_survives_as_an_alias():
    primary = make_entity("约翰·特努斯", "person", key="约翰·特努斯", mention_count=2)
    duplicate = make_entity("约翰 · 特努斯", "person", key="约翰 · 特努斯", aliases=["John Ternus"])

    merge_entities(primary, [duplicate], **MODELS)

    primary.refresh_from_db()
    assert "约翰 · 特努斯" in primary.aliases
    assert "John Ternus" in primary.aliases


def test_counts_and_timestamps_are_combined_not_replaced():
    early = timezone.now() - timezone.timedelta(days=10)
    late = timezone.now()
    primary = make_entity(
        "npm", "product", key="npm", mention_count=2, confidence=0.5, first_seen_at=late, last_seen_at=late
    )
    duplicate = make_entity(
        "npm",
        "tech",
        key="npm~tech",
        mention_count=3,
        confidence=0.9,
        first_seen_at=early,
        last_seen_at=early,
    )

    merge_entities(primary, [duplicate], **MODELS)

    primary.refresh_from_db()
    assert primary.mention_count == 5
    assert primary.confidence == 0.9
    assert primary.first_seen_at == early
    assert primary.last_seen_at == late


# --- the sweep the migration runs ---------------------------------------


def test_the_sweep_rekeys_and_folds_the_real_duplicate_shapes(article, run):
    """The duplicate shapes actually found on the live site.

    Rows go in under their pre-ADR-019 keys (lowercase, whitespace collapsed),
    which is the state the migration meets — it drops `uniq_entity_norm_type`
    before this sweep runs, precisely so these can coexist while it works.
    """
    legacy = lambda name: " ".join(name.lower().split())  # noqa: E731 - the old formula
    for left, right, types in [
        # separator-only differences
        ("小米 18 Fold", "小米18 Fold", ("product", "product")),
        ("DeepSeek V4 Flash", "DeepSeek-V4-Flash", ("model", "model")),
        # separator difference *and* a different type
        ("U-Net", "Unet", ("model", "tech")),
        ("Git Hub", "GitHub", ("org", "product")),
    ]:
        make_entity(left, types[0], key=legacy(left), mention_count=2)
        make_entity(right, types[1], key=legacy(right), mention_count=1)

    removed = merge_duplicate_entities(**MODELS, normalize=normalize_name)

    assert removed == 4
    assert Entity.objects.count() == 4
    assert {entity.normalized_name for entity in Entity.objects.all()} == {
        "小米18fold",
        "deepseekv4flash",
        "unet",
        "github",
    }
    # The winner keeps its own type; the loser's spelling is kept as an alias.
    github = Entity.objects.get(normalized_name="github")
    assert github.entity_type == "org"  # the more-mentioned row
    assert "GitHub" in github.aliases


def test_the_sweep_is_safe_to_run_twice(article, run):
    make_entity("Open AI", "org", key="open ai", mention_count=2)
    make_entity("OpenAI", "product", key="openai", mention_count=1)

    assert merge_duplicate_entities(**MODELS, normalize=normalize_name) == 1
    assert merge_duplicate_entities(**MODELS, normalize=normalize_name) == 0
    assert Entity.objects.count() == 1


def test_the_sweep_leaves_unrelated_entities_alone(article, run):
    make_entity("GPT-5", "model", mention_count=1)
    make_entity("GPT-4", "model", mention_count=1)

    assert merge_duplicate_entities(**MODELS, normalize=normalize_name) == 0
    assert Entity.objects.count() == 2
