"""Integration tests verifying that sensitive mutation handlers write AuditLog rows."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.auth.keycloak import Principal
from app.models import Agency, AuditLog
from app.routers import agencies as agencies_router
from app.routers import users as users_router
from app.schemas.agency import StatusUpdateRequest
from app.schemas.user import UserResponse
from app.services import keycloak_admin


async def _admin(email="admin@audit.com"):
    return Principal(id=str(uuid.uuid4()), email=email, display_name=None, role="admin", scopes=frozenset())


@pytest.mark.asyncio
async def test_update_agency_status_writes_audit(db):
    admin = await _admin()
    ag = await Agency.create(
        name="A", short_name="A", connection_type="API", status="draft",
        conformance_report={"passed": True, "checks": []},
    )
    await agencies_router.update_agency_status(ag.id, StatusUpdateRequest(status="active"), user=admin)
    row = await AuditLog.filter(action="agency.status_change").first()
    assert row is not None
    assert str(row.actor_id) == admin.id
    assert row.object_type == "agency"
    assert row.object_id == str(ag.id)
    assert row.detail == {"from": "draft", "to": "active"}


@pytest.mark.asyncio
async def test_deactivate_user_writes_audit(db, monkeypatch):
    admin = Principal(id="00000000-0000-0000-0000-0000000000aa", email="admin@audit.com",
                       display_name="Admin", role="admin", scopes=frozenset({"user:manage"}))
    deactivated = UserResponse(
        id="kc-1", email="target@audit.com", displayName="target", role="user",
        isActive=False, createdAt=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(keycloak_admin, "set_enabled", AsyncMock(return_value=deactivated))
    await users_router.deactivate_user("kc-1", admin=admin)
    row = await AuditLog.filter(action="user.deactivate").first()
    assert row is not None
    assert str(row.actor_id) == admin.id
    assert row.object_type == "user"
    assert row.object_id == "kc-1"
