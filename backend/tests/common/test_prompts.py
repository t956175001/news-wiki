"""Tests for the ported prompt service and its read-only endpoints."""

import pytest

from apps.common.exceptions import PromptRenderError
from apps.common.prompts import service
from apps.common.prompts.models import PromptTemplate, PromptVersion
from apps.common.prompts.seeds import PROMPT_SEEDS

pytestmark = pytest.mark.django_db

SEEDED_KEYS = {seed["key"] for seed in PROMPT_SEEDS}


@pytest.fixture
def template():
    tpl = PromptTemplate.objects.create(
        key="test.example",
        name="示例",
        default_text="hi {name}",
    )
    version = PromptVersion.objects.create(template=tpl, version_no=1, text="hi {name}", is_default=True)
    tpl.current_version = version
    tpl.save(update_fields=["current_version"])
    return tpl


def test_migration_seeds_every_documented_prompt():
    assert set(PromptTemplate.objects.values_list("key", flat=True)) == SEEDED_KEYS


def test_seeded_prompts_all_start_at_version_one():
    for key in SEEDED_KEYS:
        assert service.get_version(key) == 1


def test_render_substitutes_variables(template):
    assert service.render("test.example", {"name": "GPT-5"}) == "hi GPT-5"


def test_render_leaves_escaped_braces_as_literals():
    # The JSON skeletons inside the extraction prompts depend on `{{` -> `{`.
    rendered = service.render("wiki.extract_entities", {"raw_text": "corpus"})

    assert '"entities": [' in rendered
    assert "{{" not in rendered
    assert rendered.endswith("corpus\n")


def test_render_reports_missing_variables():
    with pytest.raises(PromptRenderError) as exc:
        service.render("wiki.extract_linkages", {"raw_text": "corpus"})

    assert exc.value.code == "PROMPT_RENDER_ERROR"
    assert "concepts_json" in exc.value.detail
    assert "entities_json" in exc.value.detail


def test_render_rejects_unknown_key():
    with pytest.raises(PromptRenderError):
        service.render("nope.missing", {})


def test_render_rejects_template_without_active_version():
    PromptTemplate.objects.create(key="test.orphan", name="孤儿", default_text="x")

    with pytest.raises(PromptRenderError):
        service.render("test.orphan", {})


def test_get_version_tracks_the_active_version(template):
    newer = PromptVersion.objects.create(template=template, version_no=2, text="hi {name}!", is_default=True)
    template.current_version = newer
    template.save(update_fields=["current_version"])

    assert service.get_version("test.example") == 2


def test_prompt_list_returns_current_version_text(client):
    response = client.get("/api/v1/prompts/")

    assert response.status_code == 200
    payload = response.json()
    assert {item["key"] for item in payload} == SEEDED_KEYS
    assert all(item["current_version"]["version_no"] == 1 for item in payload)


def test_prompt_detail_is_reachable_by_key(client):
    response = client.get("/api/v1/prompts/wiki.extract_entities/")

    assert response.status_code == 200
    assert response.json()["name"] == "实体抽取"


def test_prompt_versions_list_is_reachable(client):
    response = client.get("/api/v1/prompts/brief.daily/versions/")

    assert response.status_code == 200
    assert [v["version_no"] for v in response.json()] == [1]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_prompt_endpoints_reject_writes(client, method):
    # Prompt editing over the API was deliberately dropped; only reads remain.
    response = getattr(client, method)("/api/v1/prompts/brief.daily/")

    assert response.status_code == 405
