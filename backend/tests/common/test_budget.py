"""The daily spend cap.

Two things are being protected: that the cap is read from the runs table rather
than a counter that can drift, and that cron is exempt — a demo that stops
updating because visitors spent the budget has failed at being a demo.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.common.budget import check_budget, daily_cap, today_cost
from apps.common.exceptions import BudgetExceededError
from apps.ops.models import ExtractionRun
from apps.wiki.services.extract_pipeline import run_extraction

pytestmark = pytest.mark.django_db


def make_run(cost: str, *, days_ago: int = 0, trigger: str = "manual") -> ExtractionRun:
    run = ExtractionRun.objects.create(
        run_id=f"budget-{cost}-{days_ago}-{trigger}",
        trigger=trigger,
        status="success",
        cost_cny=Decimal(cost),
    )
    if days_ago:
        # started_at is auto_now_add.
        ExtractionRun.objects.filter(pk=run.pk).update(
            started_at=timezone.now() - dt.timedelta(days=days_ago)
        )
    return run


# --- today_cost ---------------------------------------------------------


def test_no_runs_costs_nothing():
    assert today_cost() == Decimal("0")


def test_todays_runs_are_summed():
    make_run("1.2500")
    make_run("0.7500", trigger="cron")

    assert today_cost() == Decimal("2.0000")


def test_yesterdays_spend_does_not_count_against_today():
    make_run("4.0000", days_ago=1)
    make_run("0.5000")

    assert today_cost() == Decimal("0.5000")


def test_a_running_run_already_counts():
    run = make_run("2.0000")
    run.status = "running"
    run.save(update_fields=["status"])

    assert today_cost() == Decimal("2.0000")


# --- check_budget -------------------------------------------------------


def test_spending_under_the_cap_is_allowed(settings):
    settings.LLM_DAILY_BUDGET_CNY = 5.0
    make_run("4.9999")

    check_budget("manual")  # does not raise


def test_reaching_the_cap_stops_further_spending(settings):
    settings.LLM_DAILY_BUDGET_CNY = 5.0
    make_run("5.0000")

    with pytest.raises(BudgetExceededError) as excinfo:
        check_budget("manual")

    assert excinfo.value.code == "BUDGET_EXCEEDED"
    assert "5.0" in excinfo.value.detail


def test_cron_spends_anyway(settings):
    settings.LLM_DAILY_BUDGET_CNY = 5.0
    make_run("99.0000")

    check_budget("cron")  # does not raise


def test_a_zero_cap_blocks_everything_except_cron(settings):
    settings.LLM_DAILY_BUDGET_CNY = 0.0

    with pytest.raises(BudgetExceededError):
        check_budget("manual")
    check_budget("cron")


def test_the_cap_is_read_as_a_decimal(settings):
    settings.LLM_DAILY_BUDGET_CNY = 0.1

    assert daily_cap() == Decimal("0.1")


# --- the guard where it actually sits -----------------------------------


def test_an_over_budget_run_never_reaches_the_model(settings, mock_llm):
    from apps.ingest.models import RawArticle

    settings.LLM_DAILY_BUDGET_CNY = 1.0
    make_run("1.0000")
    article = RawArticle.objects.create(
        title="测试文章",
        url="https://example.com/news/budget",
        content="OpenAI 于本周正式发布 GPT-5。",
        content_hash="budget-hash-0001",
        publish_time=timezone.now(),
    )

    run = run_extraction([article], "manual", client=mock_llm, sleep=lambda _: None)

    assert mock_llm.call_count == 0
    assert run.status == "failed"
    assert "预算" in run.error_message


def test_a_cron_run_is_not_stopped_by_the_cap(settings, mock_llm):
    from apps.ingest.models import RawArticle

    settings.LLM_DAILY_BUDGET_CNY = 0.0
    article = RawArticle.objects.create(
        title="测试文章",
        url="https://example.com/news/budget-cron",
        content="OpenAI 于本周正式发布 GPT-5。",
        content_hash="budget-hash-0002",
        publish_time=timezone.now(),
    )
    mock_llm.push_json({"entities": []})
    mock_llm.push_json({"concepts": []})
    mock_llm.push_json({"linkages": []})

    run = run_extraction([article], "cron", client=mock_llm, sleep=lambda _: None)

    assert mock_llm.call_count == 3
    assert run.status == "success"
