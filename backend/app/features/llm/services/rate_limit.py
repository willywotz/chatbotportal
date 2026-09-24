"""Rate limiter backed by Postgres (fixed-window, fail-closed)."""
import asyncio
import logging
import math
import time
from collections import defaultdict
from typing import NamedTuple, Protocol

from langchain_core.rate_limiters import BaseRateLimiter

from app.core.db import AsyncSessionLocal
from app.features.llm.repositories import rate_limit as rate_limit_repo
from app.features.llm.services.errors import LlmError


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


async def _upsert_and_count(key: str, window_start: int) -> int:
    async with AsyncSessionLocal() as session, session.begin():
        await rate_limit_repo.delete_expired(session, key, window_start)
        return await rate_limit_repo.increment_and_count(session, key, window_start)


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


_fixed_window_limiter = PostgresFixedWindowLimiter()
_queue_waiters: dict[str, int] = defaultdict(int)


async def _allow(key: str, limit: int, window_s: float) -> bool:
    result = await _fixed_window_limiter.check(key, limit=limit, window_s=window_s)
    return result.allowed


class RedisRateLimiter(BaseRateLimiter):
    def __init__(self, provider_name, rps, rpm, max_queue_size):
        self.provider_name = provider_name
        self.rps = rps
        self.rpm = rpm
        self.max_queue_size = max_queue_size

    def acquire(self, *, blocking: bool = True) -> bool:
        raise NotImplementedError("RedisRateLimiter is async-only; use aacquire")

    async def aacquire(self, *, blocking: bool = True) -> bool:
        if not self.rps and not self.rpm:
            return True
        name = self.provider_name
        if _queue_waiters[name] >= self.max_queue_size:
            raise LlmError(f"provider {name!r} rate-limit queue is full",
                           kind="queue_full", provider=name)
        _queue_waiters[name] += 1
        try:
            while True:
                if self.rps and not await _allow(f"llm:{name}:s", self.rps, 1.0):
                    await asyncio.sleep(0.02)
                    continue
                if self.rpm and not await _allow(f"llm:{name}:m", self.rpm, 60.0):
                    await asyncio.sleep(0.02)
                    continue
                return True
        finally:
            _queue_waiters[name] -= 1


_cache: dict[str, RedisRateLimiter] = {}


def limiter_for(resolved) -> RedisRateLimiter:
    existing = _cache.get(resolved.provider_name)
    if existing is not None:
        return existing
    limiter = RedisRateLimiter(resolved.provider_name, resolved.rate_limit_rps,
                               resolved.rate_limit_rpm, resolved.max_queue_size)
    _cache[resolved.provider_name] = limiter
    return limiter


def reset_cache() -> None:
    _cache.clear()
    _queue_waiters.clear()
