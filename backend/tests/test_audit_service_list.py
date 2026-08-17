"""Service-layer tests for audit-log listing (moved out of the router)."""
from app.models import AuditLog
from app.services import audit as audit_service


async def test_list_audit_log_newest_first(db):
    await AuditLog.create(actor_email="a@x.com", action="agency.update", object_type="agency", object_id="1")
    await AuditLog.create(actor_email="a@x.com", action="user.deactivate", object_type="user", object_id="2")

    rows, total = await audit_service.list_audit_log(action=None, object_type=None, actor=None, limit=50, offset=0)

    assert total == 2
    assert rows[0].action == "user.deactivate"


async def test_list_audit_log_filters_by_action(db):
    await AuditLog.create(actor_email="a@x.com", action="agency.update", object_type="agency", object_id="1")
    await AuditLog.create(actor_email="a@x.com", action="user.deactivate", object_type="user", object_id="2")

    rows, total = await audit_service.list_audit_log(
        action="agency.update", object_type=None, actor=None, limit=50, offset=0
    )

    assert total == 1
    assert rows[0].action == "agency.update"
