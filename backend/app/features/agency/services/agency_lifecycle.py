"""Agency lifecycle transition rules — mirrors the frontend lifecycle.ts table."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode
from app.features.agency.models.agency import Agency
from app.features.agency.repositories import agency as agency_repo
from app.core.events import publish

LEGAL_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["active", "disabled"],
    "active": ["maintenance", "disabled"],
    "maintenance": ["active", "disabled"],
    "disabled": ["active"],
}


def is_legal_transition(current: str, target: str) -> bool:
    return target in LEGAL_TRANSITIONS.get(current, [])


def assert_legal_transition(current: str, target: str) -> None:
    """Guard a status change against the lifecycle state machine.

    A no-op change (current == target) is allowed. Any other change must be
    listed in LEGAL_TRANSITIONS. This is the single gate for every write path.
    """
    if current == target:
        return
    if not is_legal_transition(current, target):
        raise ApiError(
            ErrorCode.INVALID_REQUEST,
            f"Illegal status transition: {current} → {target}",
            status=422,
        )


async def transition_status(session: AsyncSession, agency: Agency, new_status: str) -> str:
    assert_legal_transition(agency.status.value, new_status)
    old_status = agency.status.value
    agency.status = new_status
    agency.auto_maintenance = False
    await agency_repo.save(session, agency, update_fields=["status", "auto_maintenance", "updated_at"])
    await publish(session, "agency.status_changed", {"agency_id": str(agency.id), "from": old_status, "to": new_status})
    return old_status
