import pytest
from fastapi import HTTPException

from app.models import AuditLog
from app.models.user import User
from app.routers.audit_log import list_audit_log


async def test_list_returns_entries_newest_first(db):
    admin = await User.create(email="a@x.com", hashed_password="h", role="admin")
    await AuditLog.create(actor_email="a@x.com", action="agency.update", object_type="agency", object_id="1")
    await AuditLog.create(actor_email="a@x.com", action="user.deactivate", object_type="user", object_id="2")

    result = await list_audit_log(action=None, object_type=None, actor=None, limit=50, offset=0, _admin=admin)

    assert result["total"] == 2
    assert len(result["data"]) == 2
    assert result["data"][0]["action"] == "user.deactivate"
    assert result["data"][0]["object_id"] == "2"


async def test_filter_by_action(db):
    admin = await User.create(email="a2@x.com", hashed_password="h", role="admin")
    await AuditLog.create(actor_email="a@x.com", action="agency.update", object_type="agency", object_id="1")
    await AuditLog.create(actor_email="a@x.com", action="user.deactivate", object_type="user", object_id="2")

    result = await list_audit_log(action="agency.update", object_type=None, actor=None, limit=50, offset=0, _admin=admin)

    assert result["total"] == 1
    assert result["data"][0]["action"] == "agency.update"


async def test_filter_by_actor_email_substring(db):
    admin = await User.create(email="a3@x.com", hashed_password="h", role="admin")
    await AuditLog.create(actor_email="alice@x.com", action="user.update", object_type="user", object_id="1")
    await AuditLog.create(actor_email="bob@x.com", action="user.update", object_type="user", object_id="2")

    result = await list_audit_log(action=None, object_type=None, actor="alice", limit=50, offset=0, _admin=admin)

    assert result["total"] == 1
    assert result["data"][0]["actor_email"] == "alice@x.com"
