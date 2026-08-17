"""Rate limiters: in-process (single worker) and Redis-backed (multi worker)."""
import logging
import math
import time
import uuid
from collections import defaultdict, deque
from typing import NamedTuple, Protocol

from opentelemetry import trace
from redis.exceptions import RedisError

from app.config import settings
from app.models.rate_limit_counter import RateLimitCounter


class RateLimitResult(NamedTuple):
    allowed: bool
    retry_after: int


class RateLimiter(Protocol):
    async def check(
        self, key: str, *, limit: int, window_s: float = 60.0
    ) -> RateLimitResult: ...


class SlidingWindowLimiter:
    def __init__(self, now_fn=time.monotonic):
        self._now = now_fn
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_s: float = 60.0) -> bool:
        if limit <= 0:
            return True  # 0/None-configured = unlimited
        now = self._now()
        q = self._events[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def retry_after(self, key: str, *, window_s: float = 60.0) -> int:
        q = self._events.get(key)
        if not q:
            return 0
        return max(0, int(q[0] + window_s - self._now()) + 1)


class InProcessLimiter:
    """Async adapter over SlidingWindowLimiter for the RateLimiter interface."""

    def __init__(self, now_fn=time.monotonic):
        self._impl = SlidingWindowLimiter(now_fn=now_fn)

    async def check(
        self, key: str, *, limit: int, window_s: float = 60.0
    ) -> RateLimitResult:
        allowed = self._impl.allow(key, limit=limit, window_s=window_s)
        retry = 0 if allowed else self._impl.retry_after(key, window_s=window_s)
        return RateLimitResult(allowed, retry)


logger = logging.getLogger(__name__)

_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window_us = tonumber(ARGV[2])
local member = ARGV[3]
local t = redis.call('TIME')
local now_us = (tonumber(t[1]) * 1000000) + tonumber(t[2])
redis.call('ZREMRANGEBYSCORE', key, 0, now_us - window_us)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = 1
  if oldest[2] then
    retry = math.ceil((tonumber(oldest[2]) + window_us - now_us) / 1000000)
    if retry < 1 then retry = 1 end
  end
  return {0, retry}
end
redis.call('ZADD', key, now_us, now_us .. '-' .. member)
redis.call('PEXPIRE', key, math.ceil(window_us / 1000))
return {1, 0}
"""


class RedisHealth:
    """Tracks the rate limiter's Redis fail-open state for one worker.

    Single-threaded per worker (asyncio event loop, no await between the
    read-modify-writes here), so no locking is needed. These methods MUST stay
    synchronous and await-free — that invariant is what makes them lock-free
    correct under concurrent requests on one loop.
    """

    def __init__(self):
        self.failing = False
        self.fail_open_total = 0
        self._since = 0

    def record_failure(self) -> bool:
        """Count a fail-open. Return True only on a healthy -> failing change."""
        self.fail_open_total += 1
        if not self.failing:
            self.failing = True
            self._since = self.fail_open_total - 1
            return True
        return False

    def record_success(self) -> int | None:
        """Note a healthy call. On failing -> healthy, return how many requests
        failed open during the outage; otherwise None."""
        if self.failing:
            self.failing = False
            return self.fail_open_total - self._since
        return None


# Shared by all three limiters below: they use one Redis client, so reachability
# is a single fact per worker. An outage on any limiter flips this state, and the
# next successful call on any limiter clears it.
_redis_health = RedisHealth()

# Shared per-worker fallback used when Redis is unreachable. One instance so the
# budget is consistent across all three Redis limiters during an outage.
_fallback_limiter = InProcessLimiter()


class RedisSlidingWindowLimiter:
    """Sliding-window rate limiter backed by a Redis sorted set.

    One atomic Lua script per check, so concurrent uvicorn workers share a
    single budget. Any Redis error fails open (allows the request).
    """

    def __init__(self, client):
        self._client = client
        self._script = client.register_script(_SLIDING_WINDOW_LUA)

    async def check(
        self, key: str, *, limit: int, window_s: float = 60.0
    ) -> RateLimitResult:
        if limit <= 0:
            return RateLimitResult(True, 0)
        window_us = int(window_s * 1_000_000)
        member = uuid.uuid4().hex
        try:
            # The script returns {allowed, retry_after}; retry_after is always
            # >= 1 when blocked (the oldest in-window event expires in the future).
            allowed, retry = await self._script(
                keys=[f"rl:{key}"], args=[limit, window_us, member]
            )
        except (RedisError, OSError) as exc:  # connection/timeout — degrade
            span = trace.get_current_span()
            span.add_event(
                "rate_limit.fail_open", {"key": key, "error": type(exc).__name__}
            )
            span.add_event("rate_limit.degraded_to_inprocess", {"key": key})
            if _redis_health.record_failure():
                logger.warning(
                    "rate limiter: Redis unavailable, degrading to in-process "
                    "limiter (per-worker budget still enforced)",
                    exc_info=exc,
                )
            return await _fallback_limiter.check(key, limit=limit, window_s=window_s)
        recovered = _redis_health.record_success()
        if recovered is not None:
            logger.info(
                "rate limiter: Redis recovered after %d request(s) degraded to in-process limiter",
                recovered,
            )
        return RateLimitResult(bool(allowed), int(retry))


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


_limiter_health = LimiterHealth()


# withinlazy: read-modify-write, not atomic; concurrent workers can lose
# increments. Upgrade to a raw ON CONFLICT upsert if rate-limit precision under
# load matters. (get_or_create, not update_or_create: the latter reapplies
# defaults on update and would reset count to 0 every call.)
async def _upsert_and_count(key: str, window_start: int) -> int:
    """Fixed-window increment for one (key, window_start). Returns the new count."""
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
        if count <= limit:
            return RateLimitResult(True, 0)
        retry_us = window_start + window_us - now_us
        retry_after = max(1, math.ceil(retry_us / 1_000_000))
        return RateLimitResult(False, retry_after)


_redis_client = None


def _get_redis_client(url: str):
    """Create (once) the shared async Redis client, or None when url is empty."""
    global _redis_client
    if not url:
        return None
    if _redis_client is None:
        import redis.asyncio as aioredis

        timeout_s = settings.REDIS_SOCKET_TIMEOUT_MS / 1000
        _redis_client = aioredis.from_url(
            url,
            socket_timeout=timeout_s,
            socket_connect_timeout=timeout_s,
        )
    return _redis_client


def build_limiter():
    """Return the Postgres-backed limiter (the only backend)."""
    return PostgresFixedWindowLimiter()
