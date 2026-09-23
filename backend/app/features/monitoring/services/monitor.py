from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.agency.models.agency import Agency, AgencyStatus
from app.features.monitoring.models.check_state import AgencyCheckState, CheckStatus
from app.features.monitoring.repositories import uptime_bucket as bucket_repo
from app.features.monitoring.services import incidents as incident_svc
from app.core.config import settings


async def record_result(
    session: AsyncSession, state: AgencyCheckState, agency: Agency, *,
    ok: bool, latency_ms: int, detail: str, ts: datetime,
) -> None:
    state.last_checked_at = ts
    state.last_status = CheckStatus.up if ok else CheckStatus.down
    state.last_latency_ms = latency_ms

    await bucket_repo.record_check(session, state.agency_id, ts, ok)
    await incident_svc.apply_transition(
        session, state, ok=ok, detail=detail, failure_threshold=settings.FAILURE_THRESHOLD,
    )

    if ok and agency.status == AgencyStatus.maintenance and agency.auto_maintenance:
        agency.status = AgencyStatus.active
        agency.auto_maintenance = False
    await session.flush()
