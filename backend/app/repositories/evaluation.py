from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.evaluation import GoldenQuestion


async def all_golden_with_agency(session: AsyncSession) -> list[GoldenQuestion]:
    stmt = select(GoldenQuestion).options(selectinload(GoldenQuestion.agency))
    return list((await session.execute(stmt)).scalars().all())
