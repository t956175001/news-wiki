"""Per-IP quotas for the public demo. Contract: `docs/PRD.md` section 4.

The site is a portfolio piece with a real API key behind it. Anyone can click
"抽取"; nobody gets to click it fifty times. `budget.py` caps the day's total
spend, `DemoWriteThrottle` caps one visitor's share of it, and
`ReadRateThrottle` keeps the free-but-not-costless read endpoints (the graph
query in particular) from being hammered.
"""

from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, SimpleRateThrottle


class DemoWriteThrottle(ScopedRateThrottle):
    """`settings.DEMO_WRITE_RATE` per IP on endpoints that spend tokens.

    Off entirely when `DEMO_MODE` is false, so a self-hosted instance is not
    rate-limited against its own operator.
    """

    scope = "demo_write"

    def get_rate(self) -> str:
        # Read per request rather than at import time: it is an env knob, and
        # tests flip it with `settings.DEMO_WRITE_RATE = ...`.
        return settings.DEMO_WRITE_RATE

    def allow_request(self, request, view) -> bool:
        if not settings.DEMO_MODE:
            return True

        # ScopedRateThrottle reads the scope off the view; this one is fixed, so
        # a view opts in by listing the class and nothing else. Skipping straight
        # to SimpleRateThrottle is what makes that work.
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return SimpleRateThrottle.allow_request(self, request, view)


class ReadRateThrottle(AnonRateThrottle):
    """`settings.READ_RATE` per IP, applied to every endpoint by default.

    The read endpoints cost no tokens, but `/wiki/graph/?limit=500` is four
    unindexed aggregate queries and three gunicorn workers is the whole server.
    The ceiling is set well above what the UI does — the ops page polls every
    3s and the graph page fires a handful of requests on mount — so a real
    visitor never sees it.
    """

    scope = "read"

    def get_rate(self) -> str | None:
        # Same reasoning as DemoWriteThrottle.get_rate: env knob, and tests
        # override it with `settings.READ_RATE = ...`. Empty means "no limit" —
        # DRF treats a None rate as unthrottled, which is the escape hatch for
        # anyone self-hosting this behind their own gateway.
        return settings.READ_RATE or None
