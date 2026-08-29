"""Brief generation, and mostly one question: where do the citations come from?

The model is allowed to decide *which* sources it used. It is not allowed to
decide what those sources are. Several of these tests hand back deliberately
wrong metadata and assert that none of it survives.
"""

import datetime as dt
import json
import logging

import pytest
from django.utils import timezone

from apps.brief.models import DailyBrief
from apps.brief.services.generate import MAX_ARTICLES, generate_daily_brief
from apps.common.exceptions import AppError, ExtractionStepError
from apps.ingest.models import RawArticle
from apps.ops.models import ExtractionRun
from apps.wiki.models import Concept, Entity, Evidence, Linkage

pytestmark = pytest.mark.django_db

# The model volunteering citation metadata nobody asked it for. Nothing in the
# stored brief may ever come from these.
FAKE_URL = "https://hallucinated.example.com/never-existed"
FAKE_TITLE = "一篇不存在的文章"


def brief_payload(*, used_indexes=(1,), content="OpenAI 发布了 GPT-5[1]。", title="今日 AI 简报"):
    return {
        "title": title,
        "content_md": content,
        "used_indexes": list(used_indexes),
        # Not part of the schema, and deliberately wrong. If any of it reaches
        # the database, the whole "every claim is traceable" promise is void.
        "citations": [{"index": 1, "url": FAKE_URL, "title": FAKE_TITLE}],
    }


_UNSET = object()


def make_article(index: int = 0, *, publish_time=_UNSET, fetched_at=None) -> RawArticle:
    article = RawArticle.objects.create(
        title=f"测试文章 {index}",
        url=f"https://example.com/news/{index}",
        content="OpenAI 于本周正式发布 GPT-5。",
        content_hash=f"brief-hash-{index:04d}",
        publish_time=timezone.now() if publish_time is _UNSET else publish_time,
    )
    if fetched_at is not None:
        # auto_now_add cannot be set on create.
        RawArticle.objects.filter(pk=article.pk).update(fetched_at=fetched_at)
        article.refresh_from_db()
    return article


def generate(mock_llm, date=None, run=None):
    return generate_daily_brief(date or timezone.localdate(), run, client=mock_llm, sleep=lambda _: None)


# --- citations are the backend's, not the model's -----------------------


def test_citations_are_looked_up_in_the_database_not_taken_from_the_model(mock_llm):
    article = make_article(1)
    mock_llm.push_json(brief_payload(used_indexes=[1]))

    brief, _meta = generate(mock_llm)

    assert brief.citations == [
        {
            "index": 1,
            "raw_article_id": article.pk,
            "title": article.title,
            "url": article.url,
            "publish_time": article.publish_time.isoformat(),
        }
    ]


def test_no_fabricated_url_survives_into_the_brief(mock_llm):
    make_article(1)
    mock_llm.push_json(brief_payload(used_indexes=[1]))

    brief, _meta = generate(mock_llm)

    stored = json.dumps(brief.citations, ensure_ascii=False)
    assert FAKE_URL not in stored
    assert FAKE_TITLE not in stored


def test_an_out_of_range_index_is_ignored_with_a_warning(mock_llm, caplog):
    make_article(1)
    make_article(2)
    mock_llm.push_json(brief_payload(used_indexes=[1, 99]))

    with caplog.at_level(logging.WARNING):
        brief, _meta = generate(mock_llm)

    assert [citation["index"] for citation in brief.citations] == [1]
    assert "outside the 1-2" in caplog.text


def test_a_non_numeric_index_is_ignored(mock_llm, caplog):
    make_article(1)
    mock_llm.push_json(brief_payload(used_indexes=[1, "第二篇", None, True]))

    with caplog.at_level(logging.WARNING):
        brief, _meta = generate(mock_llm)

    assert [citation["index"] for citation in brief.citations] == [1]


def test_repeated_indexes_produce_one_citation(mock_llm):
    make_article(1)
    mock_llm.push_json(brief_payload(used_indexes=[1, 1, 1]))

    brief, _meta = generate(mock_llm)

    assert len(brief.citations) == 1


def test_citations_are_ordered_by_index(mock_llm):
    for index in range(1, 4):
        make_article(index)
    mock_llm.push_json(brief_payload(used_indexes=[3, 1, 2]))

    brief, _meta = generate(mock_llm)

    assert [citation["index"] for citation in brief.citations] == [1, 2, 3]


def test_a_brief_citing_nothing_is_still_stored(mock_llm, caplog):
    make_article(1)
    mock_llm.push_json(brief_payload(used_indexes=[]))

    with caplog.at_level(logging.WARNING):
        brief, _meta = generate(mock_llm)

    assert brief.citations == []
    assert "cites nothing" in caplog.text


# --- material selection -------------------------------------------------


def test_no_articles_raises_without_calling_the_model(mock_llm):
    with pytest.raises(AppError) as excinfo:
        generate(mock_llm)

    assert excinfo.value.code == "NO_ARTICLES"
    assert mock_llm.call_count == 0


def test_only_todays_articles_are_material(mock_llm):
    today = make_article(1)
    make_article(2, publish_time=timezone.now() - dt.timedelta(days=1))
    mock_llm.push_json(brief_payload(used_indexes=[1, 2]))

    brief, _meta = generate(mock_llm)

    assert [citation["raw_article_id"] for citation in brief.citations] == [today.pk]


def test_an_article_without_a_publish_time_is_dated_by_when_it_arrived(mock_llm):
    article = make_article(1, publish_time=None)
    mock_llm.push_json(brief_payload(used_indexes=[1]))

    brief, _meta = generate(mock_llm)

    assert brief.citations[0]["raw_article_id"] == article.pk
    assert brief.citations[0]["publish_time"] is None


def test_an_undated_article_from_another_day_is_excluded(mock_llm):
    make_article(1)
    make_article(
        2,
        publish_time=None,
        fetched_at=timezone.now() - dt.timedelta(days=3),
    )
    mock_llm.push_json(brief_payload(used_indexes=[1, 2]))

    brief, _meta = generate(mock_llm)

    assert len(brief.citations) == 1


def test_at_most_twenty_articles_are_sent(mock_llm):
    for index in range(MAX_ARTICLES + 5):
        make_article(index)
    mock_llm.push_json(brief_payload(used_indexes=[1]))

    generate(mock_llm)

    sources = json.loads(_articles_json_from(mock_llm.prompt_at(0)))
    assert len(sources) == MAX_ARTICLES
    assert [source["index"] for source in sources] == list(range(1, MAX_ARTICLES + 1))


def _articles_json_from(prompt: str) -> str:
    """Pull the rendered `articles_json` block back out of the prompt."""
    body = prompt.split("## 素材文章\n", 1)[1]
    return body.split("\n\n", 1)[0]


def test_the_runs_entities_and_relations_are_offered_as_context(mock_llm):
    article = make_article(1)
    run = ExtractionRun.objects.create(run_id="brief-run-01", trigger="cron")
    entity = Entity.objects.create(name="OpenAI", normalized_name="openai", entity_type="org")
    concept = Concept.objects.create(name="混合专家模型", namespace="technique")
    linkage = Linkage.objects.create(subject_entity=entity, predicate="采用", object_concept=concept)
    for target in ({"entity": entity}, {"linkage": linkage}):
        Evidence.objects.create(
            raw_article=article,
            snippet="OpenAI 于本周正式发布 GPT-5。",
            extraction_run=run,
            prompt_key="wiki.extract_entities",
            prompt_version=1,
            **target,
        )
    mock_llm.push_json(brief_payload(used_indexes=[1]))

    generate(mock_llm, run=run)

    prompt = mock_llm.prompt_at(0)
    assert "OpenAI" in prompt
    assert "采用" in prompt
    assert "混合专家模型" in prompt


# --- persistence --------------------------------------------------------


def test_the_brief_is_upserted_on_its_date(mock_llm):
    make_article(1)
    mock_llm.push_json(brief_payload(title="第一版"))
    mock_llm.push_json(brief_payload(title="第二版"))

    generate(mock_llm)
    brief, _meta = generate(mock_llm)

    assert DailyBrief.objects.count() == 1
    assert brief.title == "第二版"


def test_the_answering_model_is_recorded(mock_llm):
    make_article(1)
    mock_llm.push_json(brief_payload(), model="glm-4-flash")

    brief, meta = generate(mock_llm)

    assert brief.model_name == "glm-4-flash"
    assert meta.model == "glm-4-flash"


def test_the_brief_is_linked_to_the_run_that_produced_it(mock_llm):
    make_article(1)
    run = ExtractionRun.objects.create(run_id="brief-run-02", trigger="cron")
    mock_llm.push_json(brief_payload())

    brief, _meta = generate(mock_llm, run=run)

    assert brief.extraction_run == run
    assert run.briefs.count() == 1


def test_the_content_is_stored_verbatim(mock_llm):
    make_article(1)
    content = "## 模型发布\n\nOpenAI 发布了 GPT-5[1]。"
    mock_llm.push_json(brief_payload(content=content))

    brief, _meta = generate(mock_llm)

    assert brief.content_md == content


def test_tokens_are_reported_back_to_the_caller(mock_llm):
    make_article(1)
    mock_llm.push_json(brief_payload(), prompt_tokens=3200, completion_tokens=1500)

    _brief, meta = generate(mock_llm)

    assert (meta.prompt_tokens, meta.completion_tokens) == (3200, 1500)
    assert meta.status == "done"
    assert meta.attempts == 1


# --- bad model output ---------------------------------------------------


def test_invalid_json_is_retried_and_then_fails(mock_llm):
    make_article(1)
    for _ in range(3):
        mock_llm.push("这不是 JSON")

    with pytest.raises(ExtractionStepError):
        generate(mock_llm)

    assert mock_llm.call_count == 3
    assert not DailyBrief.objects.exists()


@pytest.mark.parametrize("field", ["title", "content_md", "used_indexes"])
def test_a_missing_field_is_retried_and_then_fails(mock_llm, field):
    make_article(1)
    broken = brief_payload()
    del broken[field]
    for _ in range(3):
        mock_llm.push_json(broken)

    with pytest.raises(ExtractionStepError):
        generate(mock_llm)

    assert mock_llm.call_count == 3


def test_a_retry_that_succeeds_still_writes_the_brief(mock_llm):
    make_article(1)
    mock_llm.push("{ 半个 JSON")
    mock_llm.push_json(brief_payload())

    brief, meta = generate(mock_llm)

    assert brief.pk is not None
    assert meta.attempts == 2


def test_used_indexes_must_be_an_array(mock_llm):
    make_article(1)
    broken = brief_payload()
    broken["used_indexes"] = "1,2"
    for _ in range(3):
        mock_llm.push_json(broken)

    with pytest.raises(ExtractionStepError, match="used_indexes"):
        generate(mock_llm)
