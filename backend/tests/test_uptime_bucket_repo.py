from datetime import datetime, timedelta, timezone

import pytest

from app.features.agency.models.agency import Agency
from app.features.monitoring.models.uptime_bucket import Granularity
from app.features.monitoring.repositories import uptime_bucket as repo

pytestmark = pytest.mark.asyncio


async def _agency(db_session) -> Agency:
    a = Agency(name="Bkt", status="active")
    db_session.add(a)
    await db_session.flush()
    return a


async def test_record_check_dual_writes_hour_and_day(db_session):
    a = await _agency(db_session)
    ts = datetime(2026, 9, 23, 14, 5, tzinfo=timezone.utc)
    await repo.record_check(db_session, a.id, ts, ok=True)
    await repo.record_check(db_session, a.id, ts, ok=False)
    await db_session.flush()

    hour = await repo.uptime_by_agency(db_session, ts - timedelta(hours=1), Granularity.hour)
    day = await repo.uptime_by_agency(db_session, ts - timedelta(days=1), Granularity.day)
    assert hour[str(a.id)] == (2, 1)
    assert day[str(a.id)] == (2, 1)


async def test_uptime_by_agency_respects_since(db_session):
    a = await _agency(db_session)
    old = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    recent = datetime(2026, 9, 23, 0, 0, tzinfo=timezone.utc)
    await repo.record_check(db_session, a.id, old, ok=True)
    await repo.record_check(db_session, a.id, recent, ok=True)
    await db_session.flush()

    day = await repo.uptime_by_agency(db_session, datetime(2026, 9, 10, tzinfo=timezone.utc), Granularity.day)
    assert day[str(a.id)] == (1, 1)


async def test_prune_removes_old_by_grain(db_session):
    a = await _agency(db_session)
    old_hour = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
    await repo.record_check(db_session, a.id, old_hour, ok=True)
    await db_session.flush()

    removed = await repo.prune(
        db_session,
        hour_cutoff=datetime(2026, 9, 1, tzinfo=timezone.utc),
        day_cutoff=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert removed >= 1
    hour = await repo.uptime_by_agency(db_session, old_hour - timedelta(days=1), Granularity.hour)
    assert str(a.id) not in hour
