from app.features.agency.models.agency import AgencyStatus
from app.features.agency.repositories import agency as agency_repo
from app.features.monitoring.repositories import uptime_bucket as bucket_repo
from app.features.analytics.routers.public_status import public_status
from app.core.utils import now


async def test_uptime_from_buckets_no_internal_fields(db_session):
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
