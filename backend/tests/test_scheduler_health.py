import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import scheduler
from app.features.agency.models.agency import Agency
from app.features.monitoring.models.check_state import AgencyCheckState, CheckStatus
from app.features.monitoring.repositories import check_state as cs_repo
from app.core.utils import now

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _bind_monitor(db_session, monkeypatch):
    import app.features.monitoring.services.monitor as m

    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(m, "AsyncSessionLocal", factory)


async def test_monitor_tick_records_due_agency(db_session):
    from app.features.monitoring.services import monitor
    a = Agency(name="Due", status="active", connection_type="API", endpoint_url="https://x")
    db_session.add(a)
    await db_session.flush()
    db_session.add(AgencyCheckState(agency_id=a.id, interval_seconds=300,
                                    next_check_at=now() - timedelta(seconds=1)))
    await db_session.flush()

    fake = {"success": True, "latency": "70ms"}
    with patch("app.features.monitoring.services.monitor.probe_reachability", AsyncMock(return_value=fake)):
        await scheduler.monitor_tick()

    st = await cs_repo.get(db_session, a.id)
    assert st.last_status == CheckStatus.up


async def test_start_scheduler_registers_monitor_tick(db_session):
    added = []
    with (
        patch("app.scheduler.spawn_logged", side_effect=lambda coro, *, name: (coro.close(), asyncio.ensure_future(asyncio.sleep(0)))[1]),
        patch("app.scheduler.scheduler") as mock_sched,
    ):
        mock_sched.add_job = MagicMock(side_effect=lambda fn, trigger, **k: added.append(getattr(fn, "__name__", str(fn))))
        mock_sched.start = MagicMock()
        await scheduler.start_scheduler()
    assert "monitor_tick" in added
