"""Non-admin callers must be denied `connlog:read`-scoped connection-logs routes.

Pins the deny path at the HTTP layer, mirroring tests/test_connection_logs_filter.py.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

_NO_ADMIN_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.usefixtures("db")
async def test_non_admin_denied_list_connection_logs(as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs")
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_admin_allowed_list_connection_logs(as_principal):
    as_principal()
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs")
    assert r.status_code == 200
    assert r.json()["total_items"] == 0


@pytest.mark.usefixtures("db")
async def test_non_admin_denied_connection_log_info(as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs/information")
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_admin_allowed_connection_log_info(as_principal):
    as_principal()
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs/information")
    assert r.status_code == 200
    assert r.json()["total_connections"] == 0
