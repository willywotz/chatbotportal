from datetime import timedelta

import pytest

from app.models.agency import Agency
from app.models.connection_log import ConnectionLog
from app.repositories import public_status_read as repo
from app.utils import now

pytestmark = pytest.mark.asyncio


async def test_connection_uptime_by_agency(db_session):
    ag = Agency(name="Agency A")
    db_session.add(ag)
    await db_session.flush()
    db_session.add_all([
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success"),
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success"),
        ConnectionLog(agency_id=ag.id, connection_type="API", status="error"),
    ])
    await db_session.flush()

    since = now() - timedelta(hours=24)
    counts = await repo.connection_uptime_by_agency(db_session, since)

    assert counts[str(ag.id)] == (3, 2)


async def test_list_public_agencies_excludes_draft_ordered_by_name(db_session):
    db_session.add_all([
        Agency(name="Zebra Office", status="active"),
        Agency(name="Alpha Office", status="active"),
        Agency(name="Draft Office", status="draft"),
    ])
    await db_session.flush()

    agencies = await repo.list_public_agencies(db_session)

    names = [a.name for a in agencies]
    assert names == ["Alpha Office", "Zebra Office"]
