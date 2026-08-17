from app.models import AuditLog
from app.models.user import User
from app.services.audit import record_audit


async def test_record_audit_creates_row(db):
    actor = await User.create(email="admin@x.com", hashed_password="h", role="admin")
    await record_audit(actor, "agency.status_change", object_type="agency",
                       object_id="abc-123", detail={"from": "draft", "to": "active"})
    row = await AuditLog.first()
    assert row.actor_id == actor.id
    assert row.actor_email == "admin@x.com"
    assert row.action == "agency.status_change"
    assert row.object_type == "agency"
    assert row.object_id == "abc-123"
    assert row.detail == {"from": "draft", "to": "active"}


async def test_record_audit_handles_none_actor(db):
    await record_audit(None, "system.cleanup")
    row = await AuditLog.first()
    assert row.actor_id is None and row.actor_email is None and row.action == "system.cleanup"


async def test_record_audit_never_raises_on_failure(db, monkeypatch):
    # A failure to write the audit row must NOT propagate (best-effort).
    async def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(AuditLog, "create", boom)
    await record_audit(None, "agency.update", object_type="agency", object_id="x")
