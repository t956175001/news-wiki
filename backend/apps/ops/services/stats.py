"""Aggregates for the pipeline dashboard's header cards (PRD section 3.4)."""

import datetime as dt
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.ops.models import ExtractionRun

WINDOW_DAYS = 7

# "Success rate" counts only clean runs. A partial run did produce data, but a
# rate that called it a success would report 100% on a week where every single
# run lost a step — which is exactly the week you would want to know about.
SUCCESS_STATUSES = frozenset({"success"})


def recent_stats(days: int = WINDOW_DAYS) -> dict:
    """Run counts, success rate, tokens and spend over the last *days* days."""
    since = timezone.now() - dt.timedelta(days=days)
    runs = ExtractionRun.objects.filter(started_at__gte=since)

    totals = runs.aggregate(
        total_runs=Count("id"),
        total_tokens=Sum("total_tokens"),
        total_cost_cny=Sum("cost_cny"),
    )
    by_status = {status: 0 for status, _label in ExtractionRun.STATUS}
    by_status.update(
        {row["status"]: row["count"] for row in runs.values("status").annotate(count=Count("id"))}
    )

    total_runs = totals["total_runs"]
    success_runs = sum(count for status, count in by_status.items() if status in SUCCESS_STATUSES)

    return {
        "window_days": days,
        "since": since,
        "total_runs": total_runs,
        "success_runs": success_runs,
        # Four places, not a percentage: the frontend decides how to show it.
        "success_rate": round(success_runs / total_runs, 4) if total_runs else 0.0,
        "total_tokens": totals["total_tokens"] or 0,
        "total_cost_cny": totals["total_cost_cny"] or Decimal("0"),
        "by_status": by_status,
    }
