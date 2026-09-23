import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.security.principal import Principal
from app.features.agency.models.agency import Agency
from app.core.models.connection_log import ConnectionLog
from app.features.agency.repositories import agency as agency_repo
from app.features.agency.routers import lifecycle
from app.features.agency.services import agency as agency_service
from app.core.utils import now


async def _admin():
    return Principal(id=str(uuid.uuid4()), email="a@e.com", display_name=None, role="admin", scopes=frozenset())


def _fake_result(success):
    return {
        "success": success,
        "protocol": "REST API",
        "version": "v1",
        "steps": [],
        "latency": "12ms",
        "statusCode": 200 if success else 503,
        "statusText": "OK" if success else "Service Unavailable",
        "server": "x",
        "contentType": "application/json",
    }


@pytest.mark.asyncio
async def test_test_connection_sets_reset_baseline(db_session, monkeypatch):
    admin = await _admin()
    ag = await agency_repo.create(db_session, name="A", short_name="A", connection_type="API", status="active")
    assert ag.stats_reset_at is None

    async def fake(_ct, _ag):
        return _fake_result(True)
    monkeypatch.setattr(agency_service, "test_connection", fake)

    before = now()
    await lifecycle.test_connection_endpoint(ag.id, session=db_session, _=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert refreshed.stats_reset_at is not None
    assert refreshed.stats_reset_at >= before
    rows = (await db_session.execute(
        select(ConnectionLog).where(ConnectionLog.agency_id == ag.id, ConnectionLog.action == "test")
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_successful_test_reactivates_auto_maintenance(db_session, monkeypatch):
    admin = await _admin()
    ag = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API",
        status="maintenance", auto_maintenance=True,
    )

    async def fake(_ct, _ag):
        return _fake_result(True)
    monkeypatch.setattr(agency_service, "test_connection", fake)

    await lifecycle.test_connection_endpoint(ag.id, session=db_session, _=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert refreshed.status == "active"
    assert refreshed.auto_maintenance is False


@pytest.mark.asyncio
async def test_failed_test_does_not_reactivate(db_session, monkeypatch):
    admin = await _admin()
    ag = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API",
        status="maintenance", auto_maintenance=True,
    )

    async def fake(_ct, _ag):
        return _fake_result(False)
    monkeypatch.setattr(agency_service, "test_connection", fake)

    await lifecycle.test_connection_endpoint(ag.id, session=db_session, _=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert refreshed.status == "maintenance"
    assert refreshed.auto_maintenance is True
    assert refreshed.stats_reset_at is not None


@pytest.mark.asyncio
async def test_manual_maintenance_not_reactivated_by_test(db_session, monkeypatch):
    admin = await _admin()
    ag = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API",
        status="maintenance", auto_maintenance=False,
    )

    async def fake(_ct, _ag):
        return _fake_result(True)
    monkeypatch.setattr(agency_service, "test_connection", fake)

    await lifecycle.test_connection_endpoint(ag.id, session=db_session, _=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert refreshed.status == "maintenance"


@pytest.mark.asyncio
async def test_run_connection_test_writes_no_connection_log_test_row(db_session):
    from app.features.agency.services.agency import run_connection_test
    from app.features.monitoring.repositories import check_state as cs_repo
    from app.features.monitoring.models.check_state import CheckStatus

    ag = await agency_repo.create(db_session, name="RC", connection_type="API",
                                  status="active", endpoint_url="https://x")
    await db_session.flush()
    fake = {"success": True, "latency": "12ms", "protocol": "REST API", "statusCode": 200, "steps": []}
    with patch("app.features.agency.services.agency.test_connection", AsyncMock(return_value=fake)):
        await run_connection_test(db_session, ag)

    rows = (await db_session.execute(
        select(ConnectionLog).where(ConnectionLog.agency_id == ag.id, ConnectionLog.action == "test")
    )).scalars().all()
    assert rows == []

    state = await cs_repo.get(db_session, ag.id)
    assert state is not None
    assert state.last_status == CheckStatus.up
    assert state.last_latency_ms == 12
