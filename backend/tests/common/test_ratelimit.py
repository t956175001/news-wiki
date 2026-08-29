"""Token bucket tests, run against a fake clock so nothing actually sleeps."""

import pytest

from apps.common.llm.ratelimit import TokenBucket, get_bucket, reset_bucket


class Clock:
    """Monotonic time the test controls; sleeping just moves it forward."""

    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


def _bucket(rpm, clock, burst=None):
    return TokenBucket(rpm, burst, sleep=clock.sleep, monotonic=clock.monotonic)


def test_a_full_bucket_lets_a_minutes_worth_through_without_waiting(clock):
    bucket = _bucket(60, clock)

    waits = [bucket.acquire() for _ in range(60)]

    assert waits == [0.0] * 60
    assert clock.slept == []


def test_the_next_call_waits_for_the_refill(clock):
    bucket = _bucket(60, clock)  # 1 token/second
    for _ in range(60):
        bucket.acquire()

    assert bucket.acquire() == pytest.approx(1.0)
    assert clock.slept == [pytest.approx(1.0)]


def test_callers_queue_instead_of_waking_for_the_same_token(clock):
    # Everyone sleeping for the same slot is how a token bucket turns into a
    # thundering herd; the debt has to accumulate.
    bucket = _bucket(60, clock, burst=1)
    bucket.acquire()

    first = bucket.acquire()
    clock.now = 0.0  # pretend both callers arrived at the same instant
    second = bucket.acquire()

    assert first == pytest.approx(1.0)
    assert second == pytest.approx(2.0)


def test_tokens_come_back_as_time_passes(clock):
    bucket = _bucket(60, clock, burst=5)
    for _ in range(5):
        bucket.acquire()

    clock.now += 3.0

    assert [bucket.acquire() for _ in range(3)] == [0.0, 0.0, 0.0]
    assert bucket.acquire() > 0


def test_refill_never_exceeds_the_burst_allowance(clock):
    bucket = _bucket(60, clock, burst=5)
    bucket.acquire()
    clock.now += 3600.0  # idle for an hour

    assert [bucket.acquire() for _ in range(5)] == [0.0] * 5
    assert bucket.acquire() > 0


def test_a_non_positive_rpm_disables_throttling(clock):
    bucket = _bucket(0, clock)

    assert bucket.enabled is False
    assert [bucket.acquire() for _ in range(1000)] == [0.0] * 1000
    assert clock.slept == []


def test_get_bucket_is_shared_across_callers(settings):
    settings.LLM_RATE_LIMIT_RPM = 42
    reset_bucket()

    assert get_bucket() is get_bucket()
    assert get_bucket().rate_per_minute == 42


def test_reset_bucket_picks_up_new_settings(settings):
    settings.LLM_RATE_LIMIT_RPM = 42
    reset_bucket()
    first = get_bucket()

    settings.LLM_RATE_LIMIT_RPM = 7
    reset_bucket()

    assert get_bucket() is not first
    assert get_bucket().rate_per_minute == 7
