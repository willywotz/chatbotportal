"""HTTP-level scope enforcement for audit-log, connection-logs, settings, and
the llm:read/llm:write split. One deny + one allow case per file, mirroring
tests/routers/test_staff_dashboard_scopes.py.
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

_NO_ADMIN_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.usefixtures("db")
async def test_audit_log_denied_without_scope(as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    async with await _client() as c:
        r = await c.get("/api/v1/audit-log/")
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_audit_log_allowed_with_scope(as_principal):
    as_principal(role="staff", scopes=["audit:read"])
    async with await _client() as c:
        r = await c.get("/api/v1/audit-log/")
    assert r.status_code == 200


@pytest.mark.usefixtures("db")
async def test_connection_logs_denied_without_scope(as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs")
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_connection_logs_allowed_with_scope(as_principal):
    as_principal(role="staff", scopes=["connlog:read"])
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs")
    assert r.status_code == 200


@pytest.mark.usefixtures("db")
async def test_settings_denied_without_scope(as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    async with await _client() as c:
        r = await c.get("/api/v1/settings")
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_settings_allowed_with_scope(as_principal):
    as_principal(role="staff", scopes=["settings:read"])
    async with await _client() as c:
        r = await c.get("/api/v1/settings")
    assert r.status_code == 200


@pytest.mark.usefixtures("db")
async def test_settings_write_needs_settings_write_scope(as_principal):
    as_principal(role="staff", scopes=["settings:read"])
    async with await _client() as c:
        r = await c.post("/api/v1/settings/cache/flush")
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_settings_cache_flush_allowed_with_write_scope(as_principal, monkeypatch):
    as_principal(role="staff", scopes=["settings:write"])
    monkeypatch.setattr("app.routers.settings.flush_similarity_cache", AsyncMock())
    async with await _client() as c:
        r = await c.post("/api/v1/settings/cache/flush")
    assert r.status_code == 200


@pytest.mark.usefixtures("db")
async def test_llm_read_scope_can_get_but_not_post(as_principal):
    as_principal(role="staff", scopes=["llm:read"])
    async with await _client() as c:
        get_resp = await c.get("/api/v1/language-model/providers")
        post_resp = await c.post(
            "/api/v1/language-model/providers",
            json={"name": "p", "base_url": "https://p.example"},
        )
    assert get_resp.status_code == 200
    assert post_resp.status_code == 403


@pytest.mark.usefixtures("db")
async def test_llm_write_scope_allows_post(as_principal):
    as_principal(role="staff", scopes=["llm:write"])
    async with await _client() as c:
        r = await c.post(
            "/api/v1/language-model/providers",
            json={"name": "p2", "base_url": "https://p2.example"},
        )
    assert r.status_code == 201
