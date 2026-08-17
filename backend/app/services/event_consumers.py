"""In-process consumers of domain events.

`register_consumers()` wires each handler to its event type at startup. Handlers
run asynchronously from the dispatcher, decoupled from the producer.
"""
from app.models.audit import AuditLog
from app.services.events import subscribe


async def _on_agency_status_changed(payload: dict) -> None:
    """Project an agency status change into the audit trail as a system event."""
    await AuditLog.create(
        actor_email="system:events",
        action="agency.status_changed",
        object_type="agency",
        object_id=str(payload.get("agency_id")),
        detail={"from": payload.get("from"), "to": payload.get("to")},
    )


_registered = False


def register_consumers() -> None:
    global _registered
    if _registered:
        return
    subscribe("agency.status_changed", _on_agency_status_changed)
    _registered = True
