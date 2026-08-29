"""Per-IP write quota for the public demo. Contract: `docs/PRD.md` section 4.

The site is a portfolio piece with a real API key behind it. Anyone can click
"抽取"; nobody gets to click it fifty times. `budget.py` caps the day's total
spend, this caps one visitor's share of it.
"""

from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


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
