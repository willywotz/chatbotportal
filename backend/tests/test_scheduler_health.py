import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import scheduler
from app.models import Agency, ConnectionLog
from app.repositories import agency as agency_repo

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_scheduler_session(db_session, monkeypatch):
    """Every job opens its own session; bind it to the test's connection (same
    DB transaction, via savepoints) so writes are visible/rolled back with the test."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", factory)
    # Alembic's fileConfig (disable_existing_loggers=True, run by the session-scoped
    # `_engine` fixture) disables any logger created at import time before it runs.
    logging.getLogger("app.scheduler").disabled = False


async def _mk_agency(db_session, **over) -> Agency:
    data = dict(name="A", short_name="A", connection_type="MCP", status="active",
                endpoint_url="https://x.example")
    data.update(over)
    ag = await agency_repo.create(db_session, **data)
    await db_session.flush()
    return ag


async def _logs_for(db_session, agency_id) -> list[ConnectionLog]:
    stmt = select(ConnectionLog).where(ConnectionLog.agency_id == agency_id)
    return list((await db_session.execute(stmt)).scalars().all())


async def test_scheduler_checks_mcp_agency(db_session):
    scheduler.sem = asyncio.Semaphore(5)
    ag = await _mk_agency(db_session, name="M", short_name="M", connection_type="MCP",
                          endpoint_url="https://mcp.example")
    fake = {"success": True, "latency": "120ms", "protocol": "MCP", "version": "1", "steps": []}
    with patch("app.scheduler.test_connection", AsyncMock(return_value=fake)):
        await scheduler.agency_chat_item(ag)
    logs = await _logs_for(db_session, ag.id)
    assert len(logs) == 1
    assert logs[0].connection_type == "MCP"
    assert logs[0].status == "success"
    assert logs[0].latency_ms == 120


async def test_scheduler_checks_a2a_agency(db_session):
    scheduler.sem = asyncio.Semaphore(5)
    ag = await _mk_agency(db_session, name="X", short_name="X", connection_type="A2A",
                          endpoint_url="https://a2a.example")
    fake = {"success": False, "latency": "0ms", "error": "boom", "steps": []}
    with patch("app.scheduler.test_connection", AsyncMock(return_value=fake)):
        await scheduler.agency_chat_item(ag)
    logs = await _logs_for(db_session, ag.id)
    assert logs[0].status == "error"


async def test_scheduler_checks_api_agency_via_test_connection(db_session):
    """API agencies take the same reachability path as MCP/A2A — no chat POST."""
    scheduler.sem = asyncio.Semaphore(5)
    ag = await _mk_agency(db_session, name="A", short_name="A", connection_type="API",
                          endpoint_url="https://api.example/chat",
                          expected_payload={"query": "__query__"})
    fake = {"success": True, "latency": "42ms", "protocol": "REST API", "version": "-", "steps": []}
    with patch("app.scheduler.test_connection", AsyncMock(return_value=fake)) as tc:
        await scheduler.agency_chat_item(ag)
    tc.assert_awaited_once_with("API", ag)
    logs = await _logs_for(db_session, ag.id)
    assert logs[0].connection_type == "API"
    assert logs[0].status == "success"
    assert logs[0].latency_ms == 42


async def test_scheduler_skips_draft(db_session):
    scheduler.sem = asyncio.Semaphore(5)
    ag = await _mk_agency(db_session, name="D", short_name="D", connection_type="MCP",
                          status="draft", endpoint_url="https://x")
    with patch("app.scheduler.test_connection", AsyncMock()) as tc:
        await scheduler.agency_chat_item(ag)
    tc.assert_not_called()
    assert await _logs_for(db_session, ag.id) == []


async def test_scheduler_skips_disabled(db_session):
    scheduler.sem = asyncio.Semaphore(5)
    ag = await _mk_agency(db_session, name="Z", short_name="Z", connection_type="API",
                          status="disabled", endpoint_url="https://x")
    with patch("app.scheduler.test_connection", AsyncMock()) as tc:
        await scheduler.agency_chat_item(ag)
    assert await _logs_for(db_session, ag.id) == []


async def test_health_check_job_reconciles_statuses(db_session):
    scheduler.sem = asyncio.Semaphore(5)
    with patch("app.scheduler.reconcile_statuses", AsyncMock()) as rec:
        await scheduler.agency_chat_test()
    rec.assert_awaited_once()


async def test_purge_old_connection_logs_deletes_only_stale_rows(db_session, monkeypatch):
    from datetime import timedelta

    from app.repositories import connection_log as connection_log_repo
    from app.utils import now

    ag = await _mk_agency(db_session)
    old = await connection_log_repo.create(
        db_session, agency_id=ag.id, action="test", connection_type="MCP", status="success",
    )
    old.created_at = now() - timedelta(days=scheduler.settings.CONNECTION_LOG_RETENTION_DAYS + 1)
    fresh = await connection_log_repo.create(
        db_session, agency_id=ag.id, action="test", connection_type="MCP", status="success",
    )
    await db_session.flush()

    deleted = await scheduler.purge_old_connection_logs()

    assert deleted == 1
    remaining_ids = {row.id for row in await _logs_for(db_session, ag.id)}
    assert remaining_ids == {fresh.id}


async def test_start_scheduler_uses_spawn_logged(db_session):
    """start_scheduler must use spawn_logged (not create_task) for fire-and-forget jobs."""
    captured = []

    def fake_spawn(coro, *, name):
        coro.close()  # discard without running
        captured.append(name)
        task = asyncio.ensure_future(asyncio.sleep(0))
        return task

    with (
        patch("app.scheduler.spawn_logged", side_effect=fake_spawn),
        patch("app.scheduler.scheduler") as mock_sched,
    ):
        mock_sched.add_job = MagicMock()
        mock_sched.start = MagicMock()
        await scheduler.start_scheduler()

    assert any("agency_chat_test" in n for n in captured), f"spawn_logged not called for agency_chat_test; got {captured}"
    assert any("regenerate_brief_job" in n for n in captured), f"spawn_logged not called for regenerate_brief_job; got {captured}"


async def test_agency_chat_item_times_out(db_session, caplog):
    """A hanging _run_agency_item must be cancelled and an error logged."""
    scheduler.sem = asyncio.Semaphore(5)
    ag = await _mk_agency(
        db_session, name="Slow", short_name="SL", connection_type="MCP",
        status="active", endpoint_url="https://slow.example",
    )

    async def hang(_agency):
        await asyncio.sleep(9999)

    with (
        patch("app.scheduler._run_agency_item", side_effect=hang),
        patch("app.scheduler.settings") as mock_settings,
        caplog.at_level(logging.ERROR, logger="app.scheduler"),
    ):
        mock_settings.AGENCY_CHAT_TIMEOUT = 0.01  # 10 ms
        await scheduler.agency_chat_item(ag)

    assert any("timed out" in r.getMessage().lower() for r in caplog.records if r.levelno >= logging.ERROR)
