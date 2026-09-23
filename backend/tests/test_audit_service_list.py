"""Service-layer tests for audit-log listing (moved out of the router)."""
from datetime import timedelta

import pytest

from app.repositories import audit as audit_repo
from app.services import audit as audit_service
from app.utils import now

pytestmark = pytest.mark.asyncio


async def test_list_audit_log_newest_first(db_session):
    t0 = now()
    await audit_repo.create(
        db_session, actor_email="a@x.com", action="agency.update", object_type="agency",
        object_id="1", created_at=t0,
    )
    await audit_repo.create(
        db_session, actor_email="a@x.com", action="user.deactivate", object_type="user",
        object_id="2", created_at=t0 + timedelta(seconds=1),
    )

    rows, total = await audit_service.list_audit_log(
        db_session, action=None, object_type=None, actor=None, limit=50, offset=0
    )

    assert total == 2
    assert rows[0].action == "user.deactivate"


async def test_list_audit_log_filters_by_action(db_session):
    await audit_repo.create(db_session, actor_email="a@x.com", action="agency.update", object_type="agency", object_id="1")
    await audit_repo.create(db_session, actor_email="a@x.com", action="user.deactivate", object_type="user", object_id="2")

    rows, total = await audit_service.list_audit_log(
        db_session, action="agency.update", object_type=None, actor=None, limit=50, offset=0
    )

    assert total == 1
    assert rows[0].action == "agency.update"
