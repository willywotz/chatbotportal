"""Rate limiter backed by Postgres (fixed-window, fail-closed)."""
import logging
import math
import time
from typing import NamedTuple, Protocol

from app.models.rate_limit_counter import RateLimitCounter


class RateLimitResult(NamedTuple):
    allowed: bool
    retry_after: int


class RateLimiter(Protocol):
    async def check(
        self, key: str, *, limit: int, window_s: float = 60.0
    ) -> RateLimitResult: ...


logger = logging.getLogger(__name__)


class LimiterHealth:
    """Fail-closed outage tracker. Logs once on healthy -> failing.

    Single-threaded per worker (asyncio event loop, no await between the
    read-modify-writes here), so no locking is needed. These methods MUST stay
    synchronous and await-free — that invariant is what makes them lock-free
    correct under concurrent requests on one loop.
    """

    def __init__(self):
        self.failing = False
        self.degraded_total = 0
        self._since = 0

    def record_failure(self) -> bool:
        """Count a fail-closed event. Return True only on a healthy -> failing change."""
        self.degraded_total += 1
        if not self.failing:
            self.failing = True
            self._since = self.degraded_total - 1
            return True
        return False

    def record_success(self) -> int | None:
        """Note a healthy call. On failing -> healthy, return how many requests
        degraded during the outage; otherwise None."""
        if self.failing:
            self.failing = False
            return self.degraded_total - self._since
        return None


_limiter_health = LimiterHealth()


# withinlazy: read-modify-write, not atomic; concurrent workers can lose
# increments. Upgrade to a raw ON CONFLICT upsert if rate-limit precision under
# load matters. (get_or_create, not update_or_create: the latter reapplies
# defaults on update and would reset count to 0 every call.)
async def _upsert_and_count(key: str, window_start: int) -> int:
    counter, _ = await RateLimitCounter.get_or_create(
        key=key, window_start=window_start, defaults={"count": 0}
    )
    counter.count += 1
    await counter.save(update_fields=["count"])
    return counter.count


class PostgresFixedWindowLimiter:
    """Fixed-window limiter backed by the rate_limit_counters table.

    One upsert per check. Fail-closed: a DB error returns (False, 1) so the
    caller's retry loop turns outages into backpressure.
    """

    async def check(
        self, key: str, *, limit: int, window_s: float = 60.0
    ) -> RateLimitResult:
        if limit <= 0:
            return RateLimitResult(True, 0)
        window_us = int(window_s * 1_000_000)
        now_us = int(time.time() * 1_000_000)
        window_start = now_us - (now_us % window_us)
        try:
            await RateLimitCounter.filter(
                key=key, window_start__lt=window_start
            ).delete()
            count = await _upsert_and_count(key, window_start)
        except Exception as exc:  # noqa: BLE001 — fail-closed on any DB error
            if _limiter_health.record_failure():
                logger.warning(
                    "rate limit: datastore unavailable, failing closed "
                    "(provider calls will back off and retry)",
                    exc_info=exc,
                )
            return RateLimitResult(False, 1)
        recovered = _limiter_health.record_success()
        if recovered is not None:
            logger.info(
                "rate limit: datastore recovered after %d request(s) failed closed",
                recovered,
            )
        if count <= limit:
            return RateLimitResult(True, 0)
        retry_us = window_start + window_us - now_us
        retry_after = max(1, math.ceil(retry_us / 1_000_000))
        return RateLimitResult(False, retry_after)


def build_limiter():
    return PostgresFixedWindowLimiter()
