from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.connection_log import ConnectionLog


async def create(session: AsyncSession, **fields) -> ConnectionLog:
    obj = ConnectionLog(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def get(session: AsyncSession, log_id) -> ConnectionLog | None:
    return await session.get(ConnectionLog, log_id)


async def rows_since(session: AsyncSession, agency_id, since: datetime) -> list[ConnectionLog]:
    """Rows for `agency_id` created at or after `since`, oldest first. Backs agency_health's
    error-window/uptime aggregation."""
    stmt = (
        select(ConnectionLog)
        .where(ConnectionLog.agency_id == agency_id, ConnectionLog.created_at >= since)
        .order_by(ConnectionLog.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def delete_older_than(session: AsyncSession, cutoff) -> int:
    # synchronize_session="fetch": re-select matching ids first so any already-loaded
    # ORM objects for deleted rows are correctly evicted from the identity map.
    stmt = sa_delete(ConnectionLog).where(ConnectionLog.created_at < cutoff)
    result = await session.execute(stmt, execution_options={"synchronize_session": "fetch"})
    return result.rowcount
