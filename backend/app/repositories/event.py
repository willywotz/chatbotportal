from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import DomainEvent
from app.utils import now


async def add(session: AsyncSession, event_type: str, payload: dict) -> DomainEvent:
    obj = DomainEvent(event_type=event_type, payload=payload)
    session.add(obj)
    await session.flush()
    return obj


async def pending(session: AsyncSession, limit: int) -> list[DomainEvent]:
    stmt = (
        select(DomainEvent)
        .where(DomainEvent.dispatched_at.is_(None))
        .order_by(DomainEvent.created_at, DomainEvent.id)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def mark_dispatched(session: AsyncSession, event: DomainEvent) -> None:
    event.dispatched_at = now()
    await session.flush()
