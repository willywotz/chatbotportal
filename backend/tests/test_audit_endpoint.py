import uuid
from datetime import timedelta

from app.auth.principal import Principal
from app.repositories import audit as audit_repo
from app.routers.audit_log import list_audit_log
from app.utils import now


def _admin(email: str) -> Principal:
    return Principal(id=str(uuid.uuid4()), email=email, display_name=None, role="admin", scopes=frozenset())


async def test_list_returns_entries_newest_first(db_session):
    admin = _admin("a@x.com")
    older = await audit_repo.create(db_session, actor_email="a@x.com", action="agency.update", object_type="agency", object_id="1")
    older.created_at = now() - timedelta(minutes=5)
    await db_session.flush()
    await audit_repo.create(db_session, actor_email="a@x.com", action="user.deactivate", object_type="user", object_id="2")

    result = await list_audit_log(db_session, action=None, object_type=None, actor=None, limit=50, offset=0, _admin=admin)

    assert result["total"] == 2
    assert len(result["data"]) == 2
    assert result["data"][0]["action"] == "user.deactivate"
    assert result["data"][0]["object_id"] == "2"


async def test_filter_by_action(db_session):
    admin = _admin("a2@x.com")
    await audit_repo.create(db_session, actor_email="a@x.com", action="agency.update", object_type="agency", object_id="1")
    await audit_repo.create(db_session, actor_email="a@x.com", action="user.deactivate", object_type="user", object_id="2")

    result = await list_audit_log(db_session, action="agency.update", object_type=None, actor=None, limit=50, offset=0, _admin=admin)

    assert result["total"] == 1
    assert result["data"][0]["action"] == "agency.update"


async def test_filter_by_actor_email_substring(db_session):
    admin = _admin("a3@x.com")
    await audit_repo.create(db_session, actor_email="alice@x.com", action="user.update", object_type="user", object_id="1")
    await audit_repo.create(db_session, actor_email="bob@x.com", action="user.update", object_type="user", object_id="2")

    result = await list_audit_log(db_session, action=None, object_type=None, actor="alice", limit=50, offset=0, _admin=admin)

    assert result["total"] == 1
    assert result["data"][0]["actor_email"] == "alice@x.com"
