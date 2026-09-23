import httpx
import pytest

from app.core.utils.retry import retry_async


async def test_retries_transient_then_succeeds():
    calls = {"n": 0}
    sleeps: list[float] = []

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("boom")
        return "ok"

    async def fake_sleep(s):
        sleeps.append(s)

    assert await retry_async(flaky, attempts=3, base_delay=0.5, sleep=fake_sleep) == "ok"
    assert calls["n"] == 3 and sleeps == [0.5, 1.0]  # exponential


async def test_gives_up_after_attempts():
    async def always_fails():
        raise httpx.ConnectError("boom")

    async def fake_sleep(s):
        pass

    with pytest.raises(httpx.ConnectError):
        await retry_async(always_fails, attempts=2, sleep=fake_sleep)


async def test_non_retryable_raises_immediately():
    calls = {"n": 0}

    async def bad():
        calls["n"] += 1
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        await retry_async(bad, attempts=3)
    assert calls["n"] == 1
