import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.llm import client as c
from app.services.rate_limit import RateLimitResult


@pytest.mark.asyncio
async def test_acquire_unlimited_returns_immediately():
    await c._acquire("p", None, None, 50)


@pytest.mark.asyncio
async def test_acquire_queue_full_raises():
    c._queue_waiters["pfull"] = 3
    with pytest.raises(c.LlmError) as e:
        await c._acquire("pfull", 5, 200, 3)
    assert e.value.kind == "queue_full"
    c._queue_waiters["pfull"] = 0


@pytest.mark.asyncio
async def test_acquire_waits_then_proceeds(monkeypatch):
    calls = {"n": 0}

    async def fake_check(key, *, limit, window_s):
        calls["n"] += 1
        # deny the very first rps check, then allow everything
        allowed = not (calls["n"] == 1)
        return RateLimitResult(allowed, 0 if allowed else 1)

    monkeypatch.setattr(c._provider_limiter, "check", fake_check)
    monkeypatch.setattr(c.asyncio, "sleep", AsyncMock())
    await c._acquire("pw", 5, 200, 50)
    assert calls["n"] >= 3
