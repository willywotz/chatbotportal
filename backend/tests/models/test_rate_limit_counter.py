import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.rate_limit_counter import RateLimitCounter


async def test_counter_create_and_unique_constraint(db_session):
    db_session.add(RateLimitCounter(key="llm:openrouter:s", window_start=1000, count=1))
    await db_session.flush()
    stmt = select(RateLimitCounter).where(
        RateLimitCounter.key == "llm:openrouter:s", RateLimitCounter.window_start == 1000,
    )
    row = (await db_session.execute(stmt)).scalars().one()
    assert row.count == 1


async def test_counter_unique_together_blocks_duplicate(db_session):
    db_session.add(RateLimitCounter(key="llm:openrouter:s", window_start=1000, count=1))
    await db_session.flush()
    db_session.add(RateLimitCounter(key="llm:openrouter:s", window_start=1000, count=1))
    with pytest.raises(IntegrityError):
        await db_session.flush()
