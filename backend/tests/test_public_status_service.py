"""Service-layer tests for public status/directory queries (moved out of the router)."""
import pytest

from app.features.agency.models.agency import Agency, AgencyStatus, ConnectionType
from app.features.analytics.services import public_status as public_status_service

pytestmark = pytest.mark.asyncio


async def test_public_status_uptime(db_session):
    from app.features.monitoring.repositories import uptime_bucket as bucket_repo
    from app.core.utils import now

    ag = Agency(name="A", status=AgencyStatus.active)
    db_session.add(ag)
    await db_session.flush()
    ts = now()
    for ok in (True, True, True, False):
        await bucket_repo.record_check(db_session, ag.id, ts, ok=ok)
    await db_session.flush()

    rows = await public_status_service.public_status(db_session)

    row = next(r for r in rows if r["name"] == "A")
    assert row["status"] == "active"
    assert row["uptime_24h_pct"] == 75.0
    assert row["incident_open"] is False


async def test_public_agencies_hides_draft(db_session):
    db_session.add_all([
        Agency(name="Visible", short_name="V", connection_type=ConnectionType.API, status=AgencyStatus.active),
        Agency(name="Hidden", short_name="H", connection_type=ConnectionType.API, status=AgencyStatus.draft),
    ])
    await db_session.flush()

    rows = await public_status_service.public_agencies(db_session)

    assert [r["name"] for r in rows] == ["Visible"]
    assert set(rows[0]) == {"id", "name", "short_name", "logo", "description", "connection_type", "status"}


async def test_public_status_reads_buckets_with_windows(db_session):
    from app.features.monitoring.repositories import uptime_bucket as bucket_repo
    from app.core.utils import now

    a = Agency(name="Pub", status=AgencyStatus.active)
    db_session.add(a)
    await db_session.flush()
    ts = now()
    await bucket_repo.record_check(db_session, a.id, ts, ok=True)
    await bucket_repo.record_check(db_session, a.id, ts, ok=False)
    await db_session.flush()

    out = await public_status_service.public_status(db_session)
    row = next(r for r in out if r["name"] == "Pub")
    assert row["uptime_24h_pct"] == 50.0
    assert "uptime_7d_pct" in row and "uptime_30d_pct" in row
    assert row["incident_open"] is False


async def test_public_status_null_when_no_buckets(db_session):
    a = Agency(name="Fresh", status=AgencyStatus.active)
    db_session.add(a)
    await db_session.flush()
    out = await public_status_service.public_status(db_session)
    row = next(r for r in out if r["name"] == "Fresh")
    assert row["uptime_24h_pct"] is None
