"""Daily LLM spend cap. Contract: `docs/PRD.md` section 4.

The demo is public and every visitor-triggered extraction spends real money. The
throttle in `throttling.py` limits how *often* one IP can spend; this limits how
much the whole site can spend in a day, which is the number that ends up on an
invoice.

Spend is read back from `ExtractionRun.cost_cny` rather than kept in a counter:
the runs table is already the ledger, and a counter that drifted from it would be
a second source of truth for the same money.
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.common.exceptions import BudgetExceededError
from apps.ops.models import ExtractionRun

logger = logging.getLogger(__name__)

# Cron does the work the site exists to show. If the nightly job stopped on the
# day a few visitors drained the budget, the wiki would go stale — so it spends
# regardless (PRD section 4: "cron 任务不受此限").
EXEMPT_TRIGGERS = frozenset({"cron"})

BUDGET_DETAIL = "今日 LLM 预算已用完（{spent} / {cap} 元），实时抽取暂停，明天恢复。"


def today_cost() -> Decimal:
    """Total CNY spent by runs started today, in the project timezone.

    `started_at`, not `finished_at`: a run still going has already spent its
    tokens, and waiting for it to finish would let a burst of concurrent runs
    blow past the cap while every one of them still reads zero.
    """
    total = ExtractionRun.objects.filter(started_at__date=timezone.localdate()).aggregate(
        total=Sum("cost_cny")
    )["total"]
    return total or Decimal("0")


def daily_cap() -> Decimal:
    """`LLM_DAILY_BUDGET_CNY` as a Decimal.

    Via `str()`, because the setting is a float and `Decimal(5.0)` is not 5.
    """
    return Decimal(str(settings.LLM_DAILY_BUDGET_CNY))


def check_budget(trigger: str = "manual") -> None:
    """Raise `BudgetExceededError` if today's spend has reached the cap.

    A cap of 0 blocks every non-exempt call. That is the literal reading and the
    safe one: someone who sets the budget to zero and gets billed anyway has been
    failed worse than someone who wanted "unlimited" and got a read-only demo.
    """
    if trigger in EXEMPT_TRIGGERS:
        return

    spent = today_cost()
    cap = daily_cap()
    if spent < cap:
        return

    logger.warning("Daily LLM budget reached: %s / %s CNY (trigger=%s)", spent, cap, trigger)
    raise BudgetExceededError(BUDGET_DETAIL.format(spent=spent, cap=cap))
