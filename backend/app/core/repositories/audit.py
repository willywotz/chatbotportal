from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.audit import AuditLog


async def create(session: AsyncSession, **fields) -> AuditLog:
    obj = AuditLog(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def list_and_count(
    session: AsyncSession, *, action: str | None, object_type: str | None,
    actor: str | None, offset: int, limit: int,
) -> tuple[list[AuditLog], int]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if object_type:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if actor:
        stmt = stmt.where(AuditLog.actor_email.ilike(f"%{actor}%"))
    total = (await session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )).scalar_one()
    page_stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(page_stmt)).scalars().all()
    return list(rows), total
