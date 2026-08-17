import logging

import pytest

import app.services.rate_limit as rl
from app.services.rate_limit import (
    PostgresFixedWindowLimiter,
    RateLimitResult,
)


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
