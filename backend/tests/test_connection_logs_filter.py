"""Characterization + new-filter tests for GET /connection-logs."""
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


@pytest.mark.usefixtures("db")
async def test_connection_logs_paginate_unchanged():
    ag = await Agency.create(name="A", status="active")
    for _ in range(5):
        await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="test")
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs", params={"page": 1, "limit": 2, "include_test": True})
    app.dependency_overrides.clear()
    body = r.json()
    assert len(body["items"]) == 2            # CURRENT behavior — pinned
    assert body["total_items"] == 5


@pytest.mark.usefixtures("db")
async def test_status_and_type_filters_apply_to_items_and_stats():
    ag = await Agency.create(name="A", status="active")
    await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="test")
    await ConnectionLog.create(agency=ag, connection_type="API", status="error", action="test")
    await ConnectionLog.create(agency=ag, connection_type="MCP", status="success", action="test")
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs",
                        params={"status": "success", "connection_type": "API", "include_test": True})
    app.dependency_overrides.clear()
    body = r.json()
    assert len(body["items"]) == 1
    assert body["total_items"] == 1
    assert body["successful_connections"] == 1  # stats reflect the filter too
    assert body["failed_connections"] == 0


@pytest.mark.usefixtures("db")
async def test_page_size_alias_for_limit():
    ag = await Agency.create(name="A", status="active")
    for _ in range(4):
        await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="test")
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs", params={"page_size": 2, "include_test": True})
    app.dependency_overrides.clear()
    assert len(r.json()["items"]) == 2
