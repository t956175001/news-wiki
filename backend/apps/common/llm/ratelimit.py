"""Process-wide token bucket in front of the LLM provider.

The bucket holds one minute's allowance and refills continuously. That permits a
single full-bucket burst and then holds the long-run average at
`LLM_RATE_LIMIT_RPM`, which is what the provider's quota actually measures.

Process-wide, not cluster-wide: Gunicorn runs several workers, so the effective
ceiling is `workers x rpm`. Sharing a bucket across processes would need Redis,
and Redis is off the table (`docs/DECISIONS.md`). The provider's own 429 plus the
retry in `glm.py` is the backstop; this bucket only stops a runaway loop from
hammering the API.
"""

import logging
import threading
import time
from collections.abc import Callable
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)


class TokenBucket:
    """Classic token bucket. `acquire()` blocks until a token is free."""

    def __init__(
        self,
        rate_per_minute: int,
        burst: float | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.rate_per_minute = rate_per_minute
        self._rate = rate_per_minute / 60.0
        self._burst = float(burst) if burst is not None else float(max(rate_per_minute, 1))
        self._tokens = self._burst
        self._sleep = sleep
        self._monotonic = monotonic
        self._updated_at = monotonic()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """A non-positive RPM disables throttling rather than blocking forever."""
        return self._rate > 0

    def acquire(self, tokens: float = 1.0) -> float:
        """Take *tokens*, waiting if the bucket is short. Returns seconds slept."""
        if not self.enabled:
            return 0.0

        with self._lock:
            now = self._monotonic()
            # Only the ceiling is clamped. Letting the balance go negative is what
            # makes concurrent callers queue up instead of all waking for the same
            # token, and the debt drains at exactly `_rate`.
            self._tokens = min(self._burst, self._tokens + (now - self._updated_at) * self._rate)
            self._updated_at = now
            self._tokens -= tokens
            wait = 0.0 if self._tokens >= 0 else -self._tokens / self._rate

        if wait > 0:
            logger.debug("Rate limit: waiting %.2fs for an LLM slot", wait)
            self._sleep(wait)
        return wait


@lru_cache(maxsize=1)
def get_bucket() -> TokenBucket:
    """The bucket shared by every LLM client in this process."""
    return TokenBucket(settings.LLM_RATE_LIMIT_RPM)


def reset_bucket() -> None:
    """Drop the cached bucket. For tests and for settings changes at runtime."""
    get_bucket.cache_clear()
