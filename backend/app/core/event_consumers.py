"""In-process consumers of domain events.

`register_consumers()` wires each handler to its event type at startup. Handlers
run asynchronously from the dispatcher, decoupled from the producer.
"""
from app.core.db import AsyncSessionLocal
from app.core.repositories import audit as audit_repo
from app.core.events import subscribe


async def _on_agency_status_changed(payload: dict) -> None:
    """Project an agency status change into the audit trail as a system event.

    The dispatcher only passes the event payload, so this consumer owns its
    own short-lived session (same pattern as `events.dispatch_pending`).
    """
    async with AsyncSessionLocal() as session, session.begin():
        await audit_repo.create(
            session,
            actor_email="system:events",
            action="agency.status_changed",
            object_type="agency",
            object_id=str(payload.get("agency_id")),
            detail={"from": payload.get("from"), "to": payload.get("to")},
        )


async def _on_incident_opened(payload: dict) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        await audit_repo.create(
            session,
            actor_email="system:events",
            action="agency.incident_opened",
            object_type="agency",
            object_id=str(payload.get("agency_id")),
            detail={"incident_id": payload.get("incident_id"), "reason": payload.get("detail")},
        )


async def _on_incident_closed(payload: dict) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        await audit_repo.create(
            session,
            actor_email="system:events",
            action="agency.incident_closed",
            object_type="agency",
            object_id=str(payload.get("agency_id")),
            detail={"incident_id": payload.get("incident_id")},
        )


_registered = False


def register_consumers() -> None:
    global _registered
    if _registered:
        return
    subscribe("agency.status_changed", _on_agency_status_changed)
    subscribe("agency.incident_opened", _on_incident_opened)
    subscribe("agency.incident_closed", _on_incident_closed)
    _registered = True
