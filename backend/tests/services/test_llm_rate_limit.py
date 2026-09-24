import pytest
from app.features.llm.services.errors import LlmError
from app.features.llm.services import rate_limit


class _FakeWindow:
    def __init__(self, allow_first_n):
        self.allow_first_n = allow_first_n
        self.calls = 0

    async def allow(self, key, limit, window_s):
        self.calls += 1
        return self.calls <= self.allow_first_n


@pytest.mark.asyncio
async def test_aacquire_allows_within_limit(monkeypatch):
    window = _FakeWindow(allow_first_n=10)
    monkeypatch.setattr(rate_limit, "_allow", window.allow)
    limiter = rate_limit.RedisRateLimiter("p", rps=5, rpm=100, max_queue_size=10)
    assert await limiter.aacquire() is True


@pytest.mark.asyncio
async def test_aacquire_queue_full_fast_fails(monkeypatch):
    async def never(key, limit, window_s):
        return False
    monkeypatch.setattr(rate_limit, "_allow", never)
    limiter = rate_limit.RedisRateLimiter("p", rps=1, rpm=1, max_queue_size=0)
    with pytest.raises(LlmError) as e:
        await limiter.aacquire()
    assert e.value.kind == "queue_full"


def test_sync_acquire_unsupported():
    limiter = rate_limit.RedisRateLimiter("p", rps=1, rpm=1, max_queue_size=1)
    with pytest.raises(NotImplementedError):
        limiter.acquire()


def test_no_limits_is_noop(monkeypatch):
    limiter = rate_limit.RedisRateLimiter("p", rps=None, rpm=None, max_queue_size=10)
    import asyncio
    assert asyncio.get_event_loop().run_until_complete(limiter.aacquire()) is True
