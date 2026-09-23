from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.agency.models.agency import Agency
from app.core.models.connection_log import ConnectionLog


async def connection_uptime_by_agency(session: AsyncSession, since: datetime) -> dict[str, tuple[int, int]]:
    """agency_id -> (total, ok) connection counts since `since`. Backs public_status()'s uptime map."""
    stmt = (
        select(
            ConnectionLog.agency_id,
            func.count().label("total"),
            func.sum(text("CASE WHEN status = 'success' THEN 1 ELSE 0 END")).label("ok"),
        )
        .where(ConnectionLog.created_at >= since)
        .group_by(ConnectionLog.agency_id)
    )
    rows = (await session.execute(stmt)).all()
    return {str(r.agency_id): (r.total, r.ok) for r in rows}


async def list_public_agencies(session: AsyncSession) -> list[Agency]:
    stmt = select(Agency).where(Agency.status != "draft").order_by(Agency.name)
    return list((await session.execute(stmt)).scalars().all())
