"""Query-count characterization for public_status N+1 fix."""
from sqlalchemy import event

from app.models import AgencyStatus
from app.repositories import agency as agency_repo
from app.repositories import connection_log as connection_log_repo
from app.routers.public_status import public_status


async def test_uptime_values_preserved(db_session):
    ag = await agency_repo.create(db_session, name="A", status=AgencyStatus.active)
    for ok in (True, True, True, False):
        await connection_log_repo.create(
            db_session, agency_id=ag.id, connection_type="API",
            status="success" if ok else "error", action="test",
        )
    rows = await public_status(db_session)
    assert rows == [{"name": "A", "status": "active", "uptime_24h_pct": 75.0}]


async def test_query_count_is_constant_not_per_agency(db_session):
    for i in range(5):
        ag = await agency_repo.create(db_session, name=f"A{i}", status=AgencyStatus.active)
        await connection_log_repo.create(
            db_session, agency_id=ag.id, connection_type="API", status="success", action="test",
        )

    conn = await db_session.connection()
    calls = {"n": 0}

    def counting(*_a, **_k):
        calls["n"] += 1

    event.listen(conn.sync_connection, "before_cursor_execute", counting)
    try:
        await public_status(db_session)
    finally:
        event.remove(conn.sync_connection, "before_cursor_execute", counting)
    assert calls["n"] <= 2  # NOT 2*N
