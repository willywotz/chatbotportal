from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.analytics.models.executive_brief import ExecutiveBrief


async def create(session: AsyncSession, content: str, status: str) -> ExecutiveBrief:
    obj = ExecutiveBrief(content=content, status=status)
    session.add(obj)
    await session.flush()
    return obj


async def latest(session: AsyncSession) -> ExecutiveBrief | None:
    # id (UUIDv7, time-sortable) breaks ties when generated_at is identical,
    # e.g. two rows created in the same DB transaction share one now().
    stmt = (
        select(ExecutiveBrief)
        .order_by(ExecutiveBrief.generated_at.desc(), ExecutiveBrief.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()
