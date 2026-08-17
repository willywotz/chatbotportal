import pytest

from app.models.rate_limit_counter import RateLimitCounter


@pytest.mark.asyncio
async def test_counter_create_and_unique_constraint(db):
    await RateLimitCounter.create(key="llm:openrouter:s", window_start=1000, count=1)
    row = await RateLimitCounter.get(key="llm:openrouter:s", window_start=1000)
    assert row.count == 1


@pytest.mark.asyncio
async def test_counter_unique_together_blocks_duplicate(db):
    from tortoise.exceptions import IntegrityError

    await RateLimitCounter.create(key="llm:openrouter:s", window_start=1000, count=1)
    with pytest.raises(IntegrityError):
        await RateLimitCounter.create(key="llm:openrouter:s", window_start=1000, count=1)
