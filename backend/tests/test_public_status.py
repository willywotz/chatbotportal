from app.features.agency.models.agency import AgencyStatus
from app.features.agency.repositories import agency as agency_repo
from app.core.repositories import connection_log as connection_log_repo
from app.features.analytics.routers.public_status import public_status


async def test_uptime_from_recent_logs_no_internal_fields(db_session):
    ag = await agency_repo.create(db_session, name="A", status=AgencyStatus.active)
    for ok in (True, True, True, False):
        await connection_log_repo.create(
            db_session, agency_id=ag.id, connection_type="API",
            status="success" if ok else "error", action="test",
        )

    rows = await public_status(db_session)

    assert rows == [{"name": "A", "status": "active", "uptime_24h_pct": 75.0}]
