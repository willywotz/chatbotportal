from datetime import timedelta

import pytest

from app.features.agency.models.agency import Agency
from app.core.models.connection_log import ConnectionLog
from app.core.utils import now

pytestmark = pytest.mark.asyncio


async def _agency(session, status="active"):
    ag = Agency(name="A", short_name="A", connection_type="API", status=status)
    session.add(ag)
    await session.flush()
    return ag


async def _log(session, agency, status="success", latency=300, ago_minutes=10):
    log = ConnectionLog(
        agency_id=agency.id, action="test", connection_type="API",
        status=status, latency_ms=latency, detail="",
        created_at=now() - timedelta(minutes=ago_minutes),
    )
    session.add(log)
    await session.flush()
    return log


async def test_error_window_counts_checks_and_failures(db_session):
    from app.features.agency.services.agency_health import error_window

    ag = await _agency(db_session)
    for s in ["success", "success", "error", "error", "error"]:
        await _log(db_session, ag, status=s, ago_minutes=1)
    checks, failures = await error_window(db_session, ag.id)
    assert checks == 5
    assert failures == 3


async def test_error_window_empty_returns_zeros(db_session):
    from app.features.agency.services.agency_health import error_window

    ag = await _agency(db_session)
    assert await error_window(db_session, ag.id) == (0, 0)


async def test_error_window_excludes_old_logs(db_session):
    from app.features.agency.services.agency_health import error_window

    ag = await _agency(db_session)
    await _log(db_session, ag, status="error", ago_minutes=25 * 60)
    checks, failures = await error_window(db_session, ag.id)
    assert checks == 0
    assert failures == 0


async def test_embedded_health_unknown_when_no_logs(db_session):
    from app.features.agency.services.agency_health import embedded_health

    ag = await _agency(db_session)
    h = await embedded_health(db_session, ag.id)
    assert h["state"] == "unknown"
    assert h["uptime_24h"] is None
    assert h["last_check_at"] is None


async def test_embedded_health_up(db_session):
    from app.features.agency.services.agency_health import embedded_health

    ag = await _agency(db_session)
    for _ in range(10):
        await _log(db_session, ag, status="success", latency=300)
    h = await embedded_health(db_session, ag.id)
    assert h["state"] == "up"
    assert h["uptime_24h"] == 100.0
    assert h["avg_latency_ms_24h"] == 300


async def test_embedded_health_down_when_last_failed(db_session):
    from app.features.agency.services.agency_health import embedded_health

    ag = await _agency(db_session)
    await _log(db_session, ag, status="success", ago_minutes=60)
    await _log(db_session, ag, status="error", ago_minutes=1)
    h = await embedded_health(db_session, ag.id)
    assert h["state"] == "down"


async def test_embedded_health_degraded(db_session):
    from app.features.agency.services.agency_health import embedded_health

    ag = await _agency(db_session)
    await _log(db_session, ag, status="error", ago_minutes=120)
    await _log(db_session, ag, status="error", ago_minutes=110)
    for i in range(8):
        await _log(db_session, ag, status="success", ago_minutes=10 + i)
    h = await embedded_health(db_session, ag.id)
    assert h["state"] == "degraded"
    assert h["uptime_24h"] == 80.0


async def test_health_history_bucket_counts(db_session):
    from app.features.agency.services.agency_health import health_history

    ag = await _agency(db_session)
    await _log(db_session, ag, status="success", ago_minutes=30)
    buckets = await health_history(db_session, ag.id, "24h")
    assert len(buckets) == 24
    assert {"bucket_start", "uptime_pct", "avg_latency_ms", "checks", "failures"} <= set(buckets[0].keys())
    buckets7 = await health_history(db_session, ag.id, "7d")
    assert len(buckets7) == 7 * 24
    buckets30 = await health_history(db_session, ag.id, "30d")
    assert len(buckets30) == 30


async def test_error_window_ignores_pre_reset(db_session):
    from app.features.agency.services.agency_health import error_window

    ag = await _agency(db_session)
    for _ in range(4):
        await _log(db_session, ag, status="error", ago_minutes=180)   # before reset
    await _log(db_session, ag, status="success", ago_minutes=10)        # after reset
    reset_at = now() - timedelta(hours=1)
    assert await error_window(db_session, ag.id, reset_at) == (1, 0)


async def test_embedded_health_ignores_pre_reset(db_session):
    from app.features.agency.services.agency_health import embedded_health

    ag = await _agency(db_session)
    await _log(db_session, ag, status="error", ago_minutes=180)
    await _log(db_session, ag, status="success", ago_minutes=5)
    reset_at = now() - timedelta(hours=1)
    h = await embedded_health(db_session, ag.id, reset_at)
    assert h["state"] == "up"
    assert h["uptime_24h"] == 100.0


async def test_health_history_ignores_pre_reset_keeps_grid(db_session):
    from app.features.agency.services.agency_health import health_history

    ag = await _agency(db_session)
    await _log(db_session, ag, status="error", ago_minutes=180)
    await _log(db_session, ag, status="success", ago_minutes=5)
    reset_at = now() - timedelta(hours=1)
    buckets = await health_history(db_session, ag.id, "24h", reset_at)
    assert len(buckets) == 24
    assert sum(b["checks"] for b in buckets) == 1
    assert sum(b["failures"] for b in buckets) == 0
