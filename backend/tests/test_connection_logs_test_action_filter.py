"""Test-action visibility on GET /connection-logs and /info."""
import uuid

import pytest

from app.auth.dependencies import get_current_user
from app.main import app
from app.models import Agency, ConnectionLog
from app.models.user import User
from httpx import ASGITransport, AsyncClient


def _admin():
    return User(id=uuid.uuid4(), email="a@x.io", role="admin", is_admin=True)


async def _client():
    app.dependency_overrides[get_current_user] = _admin
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _seed_one_each(ag):
    await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="test")
    await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="query")


@pytest.mark.usefixtures("db")
async def test_test_action_hidden_by_default():
    ag = await Agency.create(name="A", status="active")
    await _seed_one_each(ag)
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs")
    app.dependency_overrides.clear()
    body = r.json()
    assert [i["action"] for i in body["items"]] == ["query"]
    assert body["total_items"] == 1
    assert body["total_connections"] == 1
    assert body["successful_connections"] == 1


@pytest.mark.usefixtures("db")
async def test_include_test_shows_all():
    ag = await Agency.create(name="A", status="active")
    await _seed_one_each(ag)
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs", params={"include_test": True})
    app.dependency_overrides.clear()
    body = r.json()
    assert body["total_items"] == 2
    assert body["total_connections"] == 2
    assert {i["action"] for i in body["items"]} == {"test", "query"}


@pytest.mark.usefixtures("db")
async def test_info_excludes_test_by_default():
    ag = await Agency.create(name="A", status="active")
    await _seed_one_each(ag)
    async with await _client() as c:
        default = (await c.get("/api/v1/connection-logs/info")).json()
        with_test = (await c.get("/api/v1/connection-logs/info", params={"include_test": True})).json()
    app.dependency_overrides.clear()
    assert default["total_connections"] == 1
    assert with_test["total_connections"] == 2
