from datetime import timedelta

import pytest

from app.features.agency.repositories import agency as agency_repo
from app.core.repositories import connection_log as connection_log_repo
from app.features.agency.routers import lifecycle
from app.core.utils import now


async def _backdated_log(session, ag, status, ago_minutes):
    log = await connection_log_repo.create(
        session, agency_id=ag.id, action="test", connection_type="API",
        status=status, latency_ms=100, detail="",
    )
    log.created_at = now() - timedelta(minutes=ago_minutes)
    await session.flush()


@pytest.mark.asyncio
async def test_health_history_route_honors_reset(db_session):
    ag = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API",
        status="active", stats_reset_at=now() - timedelta(hours=1),
    )
    await _backdated_log(db_session, ag, "error", ago_minutes=180)   # before reset
    await _backdated_log(db_session, ag, "success", ago_minutes=5)    # after reset
    resp = await lifecycle.agency_health_history(ag.id, "24h", session=db_session)
    assert sum(b.checks for b in resp.data) == 1
    assert sum(b.failures for b in resp.data) == 0
