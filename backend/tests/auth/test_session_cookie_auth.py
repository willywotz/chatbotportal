from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import dependencies
from app.auth.dependencies import (
    enforce_role_allowlist, get_current_user, get_current_user_optional,
)
from app.config import settings
from app.models.user import User


def _app():
    app = FastAPI(dependencies=[Depends(enforce_role_allowlist)])

    @app.get("/api/v1/who")
    async def who(user=Depends(get_current_user)):
        return {"id": str(user.id), "role": user.role}

    @app.get("/api/v1/maybe")
    async def maybe(user=Depends(get_current_user_optional)):
        return {"anon": user is None}

    # Mirrors the real /api/v1/dashboard/stats: requires *some* authenticated
    # user via get_current_user, but the role gate is enforce_role_allowlist
    # alone (see app/routers/dashboard.py) — no internal role check here.
    @app.get("/api/v1/dashboard/stats")
    async def dashboard_stats(user=Depends(get_current_user)):
        return {"ok": True}

    return app


def test_resolve_token_alias_is_resolve_api_key():
    assert dependencies._resolve_token is dependencies._resolve_api_key


@pytest.mark.asyncio
async def test_session_cookie_authenticates(db):
    user = await User.create(email="a@b.co", hashed_password="x", role="admin", is_active=True)
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=str(user.id))):
        client = TestClient(_app())
        r = client.get("/api/v1/who", cookies={settings.SESSION_COOKIE_NAME: "sid-1"})
    assert r.status_code == 200 and r.json()["id"] == str(user.id)


@pytest.mark.asyncio
async def test_no_credential_is_anonymous_on_optional(db):
    client = TestClient(_app())
    r = client.get("/api/v1/maybe")
    assert r.json() == {"anon": True}


@pytest.mark.asyncio
async def test_bad_api_key_401s_but_bad_session_is_anon(db):
    client = TestClient(_app())
    # invalid API key -> 401 (deliberate credential)
    r1 = client.get("/api/v1/maybe", headers={"Authorization": "Bearer tcg_bogus"})
    assert r1.status_code == 401
    # unknown session cookie -> anonymous
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=None)):
        r2 = client.get("/api/v1/maybe", cookies={settings.SESSION_COOKIE_NAME: "dead"})
    assert r2.status_code == 200 and r2.json() == {"anon": True}


@pytest.mark.asyncio
async def test_bogus_header_cannot_smuggle_in_via_valid_session_cookie(db):
    """Regression: a bogus Authorization header must not let a valid session
    cookie's role slip past enforce_role_allowlist onto a staff/admin-only
    route. The header, when present, is the sole credential — no cookie
    fallback — so this must be rejected (401), not silently pass through."""
    user = await User.create(email="basic@b.co", hashed_password="x", role="user", is_active=True)
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=str(user.id))):
        client = TestClient(_app())
        r = client.get(
            "/api/v1/dashboard/stats",
            headers={"Authorization": "Bearer tcg_bogus"},
            cookies={settings.SESSION_COOKIE_NAME: "sid-1"},
        )
        assert r.status_code == 401

        # Same user, cookie only (no header): allowlist governs and denies (403).
        r2 = client.get("/api/v1/dashboard/stats", cookies={settings.SESSION_COOKIE_NAME: "sid-1"})
        assert r2.status_code == 403
