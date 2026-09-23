from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.agency.models.agency import Agency
from app.features.monitoring.models.incident import Incident
from app.core.utils import now


async def recent(session: AsyncSession, *, limit: int = 20) -> list[tuple[Incident, str]]:
    stmt = (
        select(Incident, Agency.name)
        .join(Agency, Agency.id == Incident.agency_id)
        .order_by(Incident.ended_at.is_(None).desc(), Incident.started_at.desc())
        .limit(limit)
    )
    return [(inc, name) for inc, name in (await session.execute(stmt)).all()]


async def find_open(session: AsyncSession, agency_id) -> Incident | None:
    stmt = select(Incident).where(Incident.agency_id == agency_id, Incident.ended_at.is_(None)).limit(1)
    return (await session.execute(stmt)).scalars().first()


async def agencies_with_open_incident(session: AsyncSession) -> set[str]:
    stmt = select(Incident.agency_id).where(Incident.ended_at.is_(None))
    return {str(r) for r in (await session.execute(stmt)).scalars().all()}


async def open_incident(session: AsyncSession, agency_id, detail: str) -> Incident:
    obj = Incident(agency_id=agency_id, detail=detail)
    session.add(obj)
    await session.flush()
    return obj


async def close_incident(session: AsyncSession, incident: Incident) -> None:
    incident.ended_at = now()
    await session.flush()
