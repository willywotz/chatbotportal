"""Public, unauthenticated agency status and directory queries — no internal fields."""
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.analytics.repositories import public_status_read as public_status_repo
from app.core.utils import now


async def public_status(session: AsyncSession) -> list[dict]:
    cutoff = now() - timedelta(hours=24)
    counts = await public_status_repo.connection_uptime_by_agency(session, cutoff)
    agencies = await public_status_repo.list_public_agencies(session)

    out: list[dict] = []
    for ag in agencies:
        total, ok = counts.get(str(ag.id), (0, 0))
        uptime = round(ok / total * 100, 1) if total else None
        out.append({"name": ag.name, "status": ag.status.value, "uptime_24h_pct": uptime})
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
