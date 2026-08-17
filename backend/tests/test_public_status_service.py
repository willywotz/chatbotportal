"""Service-layer tests for public status/directory queries (moved out of the router)."""
from app.models import Agency, ConnectionLog
from app.services import public_status as public_status_service


async def test_public_status_uptime(db):
    ag = await Agency.create(name="A", status="active")
    for ok in (True, True, True, False):
        await ConnectionLog.create(agency=ag, connection_type="API",
                                    status="success" if ok else "error", action="test")

    rows = await public_status_service.public_status()

    assert rows == [{"name": "A", "status": "active", "uptime_24h_pct": 75.0}]


async def test_public_agencies_hides_draft(db):
    await Agency.create(name="Visible", short_name="V", connection_type="API", status="active")
    await Agency.create(name="Hidden", short_name="H", connection_type="API", status="draft")

    rows = await public_status_service.public_agencies()

    assert [r["name"] for r in rows] == ["Visible"]
    assert set(rows[0]) == {"id", "name", "short_name", "logo", "description", "connection_type", "status"}
