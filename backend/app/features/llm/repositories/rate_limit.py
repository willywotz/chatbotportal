from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.llm.models.rate_limit_counter import RateLimitCounter


async def delete_expired(session: AsyncSession, key: str, window_start: int) -> None:
    await session.execute(
        delete(RateLimitCounter).where(
            RateLimitCounter.key == key, RateLimitCounter.window_start < window_start,
        )
    )


async def increment_and_count(session: AsyncSession, key: str, window_start: int) -> int:
    """Atomically upsert the (key, window_start) counter and return the new count."""
    stmt = (
        pg_insert(RateLimitCounter)
        .values(key=key, window_start=window_start, count=1)
        .on_conflict_do_update(
            index_elements=[RateLimitCounter.key, RateLimitCounter.window_start],
            set_={"count": RateLimitCounter.count + 1},
        )
        .returning(RateLimitCounter.count)
    )
    return (await session.execute(stmt)).scalar_one()
