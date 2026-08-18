"""Agency lifecycle transition rules — mirrors the frontend lifecycle.ts table."""

from app.errors import ApiError, ErrorCode
from app.models.agency import Agency
from app.services.events import publish

LEGAL_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["active", "disabled"],
    "active": ["maintenance", "disabled"],
    "maintenance": ["active", "disabled"],
    "disabled": ["active"],
}


def is_legal_transition(current: str, target: str) -> bool:
    return target in LEGAL_TRANSITIONS.get(current, [])


async def transition_status(agency: Agency, new_status: str) -> str:
    if not is_legal_transition(agency.status.value, new_status):
        raise ApiError(
            ErrorCode.INVALID_REQUEST,
            f"Illegal status transition: {agency.status.value} → {new_status}",
            status=422,
        )
    if agency.status.value == "draft" and new_status == "active":
        report = agency.conformance_report or {}
        if not report.get("passed"):
            raise ApiError(ErrorCode.INVALID_REQUEST, "conformance test must pass before activation", status=400)
    old_status = agency.status.value
    agency.status = new_status
    agency.auto_maintenance = False
    await agency.save(update_fields=["status", "auto_maintenance", "updated_at"])
    await publish("agency.status_changed", {"agency_id": str(agency.id), "from": old_status, "to": new_status})
    return old_status
