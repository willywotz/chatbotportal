from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.agency.models.agency import Agency


async def list_public_agencies(session: AsyncSession) -> list[Agency]:
    stmt = select(Agency).where(Agency.status != "draft").order_by(Agency.name)
    return list((await session.execute(stmt)).scalars().all())
