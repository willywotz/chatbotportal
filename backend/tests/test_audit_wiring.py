"""Integration tests verifying that sensitive mutation handlers write AuditLog rows."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.security.principal import Principal
from app.features.agency.models.agency import AgencyStatus
from app.core.models.audit import AuditLog
from app.features.agency.repositories import agency as agency_repo
from app.features.agency import routers as agencies_router
from app.features.identity.routers import users as users_router
from app.features.agency.schemas.agency import StatusUpdateRequest
from app.features.identity.schemas.user import UserResponse
from app.features.identity.services import user_admin


def _admin(email="admin@audit.com"):
    return Principal(id=str(uuid.uuid4()), email=email, display_name=None, role="admin", scopes=frozenset())


async def _find(session, action: str) -> AuditLog | None:
    stmt = select(AuditLog).where(AuditLog.action == action)
    return (await session.execute(stmt)).scalars().first()


async def test_update_agency_status_writes_audit(db_session):
    admin = _admin()
    ag = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API", status=AgencyStatus.draft,
        conformance_report={"passed": True, "checks": []},
    )
    await agencies_router.update_agency_status(ag.id, StatusUpdateRequest(status="active"), db_session, user=admin)
    row = await _find(db_session, "agency.status_change")
    assert row is not None
    assert str(row.actor_id) == admin.id
    assert row.object_type == "agency"
    assert row.object_id == str(ag.id)
    assert row.detail == {"from": "draft", "to": "active"}


async def test_deactivate_user_writes_audit(db_session, monkeypatch):
    admin = Principal(id="00000000-0000-0000-0000-0000000000aa", email="admin@audit.com",
                       display_name="Admin", role="admin", scopes=frozenset({"user:manage"}))
    target_id = "00000000-0000-0000-0000-0000000000bb"
    deactivated = UserResponse(
        id=target_id, email="target@audit.com", displayName="target", role="user",
        isActive=False, createdAt=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(user_admin, "set_enabled", AsyncMock(return_value=deactivated))
    await users_router.deactivate_user(target_id, db_session, admin=admin)
    row = await _find(db_session, "user.deactivate")
    assert row is not None
    assert str(row.actor_id) == admin.id
    assert row.object_type == "user"
    assert row.object_id == target_id
