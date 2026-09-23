from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.monitoring.models.check_state import AgencyCheckState
from app.features.monitoring.repositories import incident as incident_repo
from app.core.events import publish


async def apply_transition(
    session: AsyncSession, state: AgencyCheckState, *, ok: bool, detail: str, failure_threshold: int,
) -> None:
    if ok:
        state.consecutive_failures = 0
        if state.current_incident_id is not None:
            incident = await incident_repo.find_open(session, state.agency_id)
            if incident is not None:
                await incident_repo.close_incident(session, incident)
                await publish(session, "agency.incident_closed", {
                    "agency_id": str(state.agency_id),
                    "incident_id": str(incident.id),
                })
            state.current_incident_id = None
        return

    state.consecutive_failures += 1
    if state.consecutive_failures >= failure_threshold and state.current_incident_id is None:
        incident = await incident_repo.open_incident(session, state.agency_id, detail)
        state.current_incident_id = incident.id
        await publish(session, "agency.incident_opened", {
            "agency_id": str(state.agency_id),
            "incident_id": str(incident.id),
            "detail": detail,
        })
