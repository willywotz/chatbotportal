"""Query-count characterization for public_status: constant, not per-agency."""
from sqlalchemy import event

from app.features.agency.models.agency import AgencyStatus
from app.features.agency.repositories import agency as agency_repo
from app.features.monitoring.repositories import uptime_bucket as bucket_repo
from app.features.analytics.routers.public_status import public_status
from app.core.utils import now


async def test_uptime_values_preserved(db_session):
    ag = await agency_repo.create(db_session, name="A", status=AgencyStatus.active)
    ts = now()
    for ok in (True, True, True, False):
        await bucket_repo.record_check(db_session, ag.id, ts, ok=ok)
    rows = await public_status(db_session)
    assert rows == [{
        "name": "A", "status": "active",
        "uptime_24h_pct": 75.0, "uptime_7d_pct": 75.0, "uptime_30d_pct": 75.0,
        "incident_open": False,
    }]


async def test_query_count_is_constant_not_per_agency(db_session):
    ts = now()
    for i in range(5):
        ag = await agency_repo.create(db_session, name=f"A{i}", status=AgencyStatus.active)
        await bucket_repo.record_check(db_session, ag.id, ts, ok=True)

    conn = await db_session.connection()
    calls = {"n": 0}

    def counting(*_a, **_k):
        calls["n"] += 1

    event.listen(conn.sync_connection, "before_cursor_execute", counting)
    try:
        await public_status(db_session)
    finally:
        event.remove(conn.sync_connection, "before_cursor_execute", counting)
    assert calls["n"] <= 5  # constant (3 bucket windows + agencies + open incidents), NOT per-agency
