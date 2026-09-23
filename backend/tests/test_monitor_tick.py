from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.agency.models.agency import Agency
from app.features.monitoring.models.check_state import AgencyCheckState, CheckStatus
from app.features.monitoring.services import monitor
from app.features.monitoring.repositories import check_state as cs_repo
from app.core.utils import now

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _bind_monitor(db_session, monkeypatch):
    """monitor.run_tick opens its own AsyncSessionLocal; bind it to the test's
    connection (savepoints) so writes are visible and rolled back with the test."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(monitor, "AsyncSessionLocal", factory)


async def test_probe_agency_retries_then_succeeds():
    calls = {"n": 0}

    async def flaky(_ct, _ag):
        calls["n"] += 1
        if calls["n"] < 2:
            return {"success": False, "latency": "0ms", "error": "boom"}
        return {"success": True, "latency": "30ms"}

    with patch("app.features.monitoring.services.monitor.test_connection", side_effect=flaky):
        ag = Agency(name="P", status="active", connection_type="API", endpoint_url="https://x")
        result = await monitor.probe_agency(ag, retry_max=3, base_delay_ms=1)
    assert result["success"] is True
    assert calls["n"] == 2


async def test_probe_agency_transport_error_returns_down():
    async def boom(_ct, _ag):
        raise RuntimeError("dns exploded")

    with patch("app.features.monitoring.services.monitor.test_connection", side_effect=boom):
        ag = Agency(name="P", status="active", connection_type="API", endpoint_url="https://x")
        result = await monitor.probe_agency(ag, retry_max=2, base_delay_ms=1)
    assert result["success"] is False
    assert "dns exploded" in result["error"]


async def test_run_tick_records_claimed_agency(db_session):
    a = Agency(name="Tick", status="active", connection_type="API", endpoint_url="https://x")
    db_session.add(a)
    await db_session.flush()
    db_session.add(AgencyCheckState(agency_id=a.id, interval_seconds=300,
                                    next_check_at=now() - timedelta(seconds=1)))
    await db_session.flush()

    fake = {"success": True, "latency": "88ms"}
    with patch("app.features.monitoring.services.monitor.test_connection", AsyncMock(return_value=fake)):
        recorded = await monitor.run_tick()

    assert recorded >= 1
    st = await cs_repo.get(db_session, a.id)
    assert st.last_status == CheckStatus.up and st.last_latency_ms == 88
