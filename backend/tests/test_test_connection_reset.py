import uuid

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
    log = (await db_session.execute(
        select(ConnectionLog).where(ConnectionLog.agency_id == ag.id)
    )).scalars().first()
    assert log is not None
    assert log.created_at >= refreshed.stats_reset_at


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
