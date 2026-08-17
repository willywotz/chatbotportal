import pytest

from app.models import Agency, ConnectionLog
from app.models.user import User
from app.routers.agencies import lifecycle
from app.services import agency as agency_service
from app.utils import now


async def _admin():
    return await User.create(email="a@e.com", hashed_password="x", role="admin", is_active=True)


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
async def test_test_connection_sets_reset_baseline(db, monkeypatch):
    admin = await _admin()
    ag = await Agency.create(name="A", short_name="A", connection_type="API", status="active")
    assert ag.stats_reset_at is None

    async def fake(_ct, _ag):
        return _fake_result(True)
    monkeypatch.setattr(agency_service, "test_connection", fake)

    before = now()
    await lifecycle.test_connection_endpoint(ag.id, _=admin)
    refreshed = await Agency.get(id=ag.id)
    assert refreshed.stats_reset_at is not None
    assert refreshed.stats_reset_at >= before
    # the test's own log lands in-window
    log = await ConnectionLog.filter(agency_id=ag.id).first()
    assert log is not None
    assert log.created_at >= refreshed.stats_reset_at


@pytest.mark.asyncio
async def test_successful_test_reactivates_auto_maintenance(db, monkeypatch):
    admin = await _admin()
    ag = await Agency.create(
        name="A", short_name="A", connection_type="API",
        status="maintenance", auto_maintenance=True,
    )

    async def fake(_ct, _ag):
        return _fake_result(True)
    monkeypatch.setattr(agency_service, "test_connection", fake)

    await lifecycle.test_connection_endpoint(ag.id, _=admin)
    refreshed = await Agency.get(id=ag.id)
    assert refreshed.status == "active"
    assert refreshed.auto_maintenance is False


@pytest.mark.asyncio
async def test_failed_test_does_not_reactivate(db, monkeypatch):
    admin = await _admin()
    ag = await Agency.create(
        name="A", short_name="A", connection_type="API",
        status="maintenance", auto_maintenance=True,
    )

    async def fake(_ct, _ag):
        return _fake_result(False)
    monkeypatch.setattr(agency_service, "test_connection", fake)

    await lifecycle.test_connection_endpoint(ag.id, _=admin)
    refreshed = await Agency.get(id=ag.id)
    assert refreshed.status == "maintenance"
    assert refreshed.auto_maintenance is True
    # baseline still set, and the single in-window log is the failure
    assert refreshed.stats_reset_at is not None


@pytest.mark.asyncio
async def test_manual_maintenance_not_reactivated_by_test(db, monkeypatch):
    admin = await _admin()
    ag = await Agency.create(
        name="A", short_name="A", connection_type="API",
        status="maintenance", auto_maintenance=False,
    )

    async def fake(_ct, _ag):
        return _fake_result(True)
    monkeypatch.setattr(agency_service, "test_connection", fake)

    await lifecycle.test_connection_endpoint(ag.id, _=admin)
    refreshed = await Agency.get(id=ag.id)
    assert refreshed.status == "maintenance"
