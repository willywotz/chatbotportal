"""Service-layer tests for public status/directory queries (moved out of the router)."""
import pytest

from app.features.agency.models.agency import Agency, AgencyStatus, ConnectionType
from app.core.models.connection_log import ConnectionLog
from app.features.analytics.services import public_status as public_status_service

pytestmark = pytest.mark.asyncio


async def test_public_status_uptime(db_session):
    ag = Agency(name="A", status=AgencyStatus.active)
    db_session.add(ag)
    await db_session.flush()
    db_session.add_all([
        ConnectionLog(agency_id=ag.id, connection_type="API",
                       status="success" if ok else "error", action="test")
        for ok in (True, True, True, False)
    ])
    await db_session.flush()

    rows = await public_status_service.public_status(db_session)

    assert rows == [{"name": "A", "status": "active", "uptime_24h_pct": 75.0}]


async def test_public_agencies_hides_draft(db_session):
    db_session.add_all([
        Agency(name="Visible", short_name="V", connection_type=ConnectionType.API, status=AgencyStatus.active),
        Agency(name="Hidden", short_name="H", connection_type=ConnectionType.API, status=AgencyStatus.draft),
    ])
    await db_session.flush()

    rows = await public_status_service.public_agencies(db_session)

    assert [r["name"] for r in rows] == ["Visible"]
    assert set(rows[0]) == {"id", "name", "short_name", "logo", "description", "connection_type", "status"}
