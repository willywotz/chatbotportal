import logging

import pytest

import app.services.rate_limit as rl
from app.services.rate_limit import (
    PostgresFixedWindowLimiter,
    RateLimitResult,
    build_limiter,
)


def test_factory_returns_postgres_limiter():
    lim = build_limiter()
    assert isinstance(lim, PostgresFixedWindowLimiter)


@pytest.mark.asyncio
async def test_under_limit_increments_and_allows(db):
    lim = PostgresFixedWindowLimiter()
    r = await lim.check("llm:p:s", limit=3, window_s=1.0)
    assert r == RateLimitResult(True, 0)


@pytest.mark.asyncio
async def test_at_limit_denies_with_retry_after_in_window(db):
    lim = PostgresFixedWindowLimiter()
    for _ in range(3):
        assert await lim.check("llm:p:s", limit=3, window_s=60.0) == RateLimitResult(True, 0)
    r = await lim.check("llm:p:s", limit=3, window_s=60.0)
    assert r.allowed is False
    assert 1 <= r.retry_after <= 60


@pytest.mark.asyncio
async def test_zero_limit_short_circuits_no_write(db):
    from app.models.rate_limit_counter import RateLimitCounter

    lim = PostgresFixedWindowLimiter()
    assert await lim.check("llm:p:s", limit=0, window_s=60.0) == RateLimitResult(True, 0)
    assert await RateLimitCounter.filter(key="llm:p:s").count() == 0


@pytest.mark.asyncio
async def test_new_window_resets_counter(db):
    lim = PostgresFixedWindowLimiter()
    # Fill a window far in the past; prune must drop it and allow again.
    from app.models.rate_limit_counter import RateLimitCounter
    await RateLimitCounter.create(key="llm:p:s", window_start=1, count=3)

    r = await lim.check("llm:p:s", limit=3, window_s=60.0)
    assert r == RateLimitResult(True, 0)


@pytest.mark.asyncio
async def test_db_error_fails_closed_and_logs_once(db, monkeypatch, caplog):
    lim = PostgresFixedWindowLimiter()
    rl._limiter_health.failing = False
    rl._limiter_health.degraded_total = 0

    async def boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(rl, "_upsert_and_count", boom)

    with caplog.at_level(logging.WARNING, logger="app.services.rate_limit"):
        r1 = await lim.check("llm:p:s", limit=3, window_s=60.0)
        r2 = await lim.check("llm:p:s", limit=3, window_s=60.0)
    assert r1 == RateLimitResult(False, 1)
    assert r2 == RateLimitResult(False, 1)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "rate limit" in warnings[0].getMessage().lower()


@pytest.mark.asyncio
async def test_recovery_logs_degraded_count_once(db, monkeypatch, caplog):
    """Fail closed, then succeed: the failing->healthy change logs the count
    of requests that degraded during the outage, exactly once."""
    lim = PostgresFixedWindowLimiter()
    rl._limiter_health.failing = False
    rl._limiter_health.degraded_total = 0

    calls = {"n": 0}

    async def boom_then_ok(*a, **kw):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("db down")
        return 1  # under the limit

    monkeypatch.setattr(rl, "_upsert_and_count", boom_then_ok)

    with caplog.at_level(logging.INFO, logger="app.services.rate_limit"):
        await lim.check("llm:p:s", limit=3, window_s=60.0)  # fail 1
        await lim.check("llm:p:s", limit=3, window_s=60.0)  # fail 2
        r3 = await lim.check("llm:p:s", limit=3, window_s=60.0)  # recover
        r4 = await lim.check("llm:p:s", limit=3, window_s=60.0)  # still healthy

    assert r3 == RateLimitResult(True, 0)
    assert r4 == RateLimitResult(True, 0)
    assert rl._limiter_health.failing is False
    infos = [
        r for r in caplog.records
        if r.levelno == logging.INFO and "recover" in r.getMessage().lower()
    ]
    assert len(infos) == 1
    assert "2" in infos[0].getMessage()  # two requests degraded during the outage
