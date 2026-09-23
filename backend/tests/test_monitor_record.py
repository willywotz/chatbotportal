import pytest
from datetime import datetime, timezone

from app.features.agency.models.agency import Agency
from app.features.monitoring.models.check_state import AgencyCheckState, CheckStatus
from app.features.monitoring.models.uptime_bucket import Granularity
from app.features.monitoring.services import monitor
from app.features.monitoring.repositories import uptime_bucket as bucket_repo
from app.core.utils import now

pytestmark = pytest.mark.asyncio


async def _fixture(db_session, **agency_over):
    agency_over.setdefault("status", "active")
    a = Agency(name="Rec", **agency_over)
    db_session.add(a)
    await db_session.flush()
    st = AgencyCheckState(agency_id=a.id, interval_seconds=300, next_check_at=now())
    db_session.add(st)
    await db_session.flush()
    return a, st


async def test_record_success_updates_state_and_bucket(db_session):
    a, st = await _fixture(db_session)
    ts = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)
    await monitor.record_result(db_session, st, a, ok=True, latency_ms=120, detail="ok", ts=ts)
    await db_session.flush()

    assert st.last_status == CheckStatus.up
    assert st.last_latency_ms == 120
    hour = await bucket_repo.uptime_by_agency(db_session, ts.replace(hour=0), Granularity.hour)
    assert hour[str(a.id)] == (1, 1)


async def test_record_failure_marks_down(db_session):
    a, st = await _fixture(db_session)
    await monitor.record_result(db_session, st, a, ok=False, latency_ms=0, detail="boom", ts=now())
    assert st.last_status == CheckStatus.down
    assert st.consecutive_failures == 1


async def test_success_recovers_maintenance_agency(db_session):
    a, st = await _fixture(db_session, status="maintenance", auto_maintenance=True)
    await monitor.record_result(db_session, st, a, ok=True, latency_ms=50, detail="ok", ts=now())
    assert a.status.value == "active"
    assert a.auto_maintenance is False
