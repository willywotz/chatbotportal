import uuid

import pytest
from sqlalchemy import select

from app.core.security.principal import Principal
from app.core.models.audit import AuditLog
from app.core.audit import record_audit

pytestmark = pytest.mark.asyncio


async def test_record_audit_creates_row(db_session):
    actor = Principal(id=str(uuid.uuid4()), email="admin@x.com", display_name=None, role="admin", scopes=frozenset())
    await record_audit(db_session, actor, "agency.status_change", object_type="agency",
                        object_id="abc-123", detail={"from": "draft", "to": "active"})
    row = (await db_session.execute(select(AuditLog))).scalars().one()
    assert str(row.actor_id) == actor.id
    assert row.actor_email == "admin@x.com"
    assert row.action == "agency.status_change"
    assert row.object_type == "agency"
    assert row.object_id == "abc-123"
    assert row.detail == {"from": "draft", "to": "active"}


async def test_record_audit_handles_none_actor(db_session):
    await record_audit(db_session, None, "system.cleanup")
    row = (await db_session.execute(select(AuditLog))).scalars().one()
    assert row.actor_id is None and row.actor_email is None and row.action == "system.cleanup"


async def test_record_audit_never_raises_on_failure(db_session, monkeypatch):
    # A failure to write the audit row must NOT propagate (best-effort).
    from app.core.repositories import audit as audit_repo

    async def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(audit_repo, "create", boom)
    await record_audit(db_session, None, "agency.update", object_type="agency", object_id="x")
