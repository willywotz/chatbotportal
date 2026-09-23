"""Public, unauthenticated agency status and directory queries — no internal fields."""
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.analytics.repositories import public_status_read as public_status_repo
from app.features.monitoring.repositories import incident as incident_repo
from app.features.monitoring.repositories import uptime_bucket as bucket_repo
from app.features.monitoring.models.uptime_bucket import Granularity
from app.core.utils import now


def _pct(counts: dict, agency_id: str):
    total, ok = counts.get(agency_id, (0, 0))
    return round(ok / total * 100, 1) if total else None


async def public_status(session: AsyncSession) -> list[dict]:
    moment = now()
    h24 = await bucket_repo.uptime_by_agency(session, moment - timedelta(hours=24), Granularity.hour)
    d7 = await bucket_repo.uptime_by_agency(session, moment - timedelta(days=7), Granularity.hour)
    d30 = await bucket_repo.uptime_by_agency(session, moment - timedelta(days=30), Granularity.day)
    agencies = await public_status_repo.list_public_agencies(session)
    open_incidents = await incident_repo.agencies_with_open_incident(session)

    out: list[dict] = []
    for ag in agencies:
        aid = str(ag.id)
        out.append({
            "name": ag.name,
            "status": ag.status.value,
            "uptime_24h_pct": _pct(h24, aid),
            "uptime_7d_pct": _pct(d7, aid),
            "uptime_30d_pct": _pct(d30, aid),
            "incident_open": aid in open_incidents,
        })
    return out


async def public_agencies(session: AsyncSession) -> list[dict]:
    """Display-safe agency list for the public portal — no internals."""
    agencies = await public_status_repo.list_public_agencies(session)
    return [
        {
            "id": str(ag.id),
            "name": ag.name,
            "short_name": ag.short_name,
            "logo": ag.logo,
            "description": ag.description,
            "connection_type": ag.connection_type.value,
            "status": ag.status.value,
        }
        for ag in agencies
    ]
