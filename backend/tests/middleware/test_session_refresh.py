from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.middleware.session_refresh import SessionRefreshMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(SessionRefreshMiddleware)

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    return app


def test_near_expiry_session_is_rotated():
    with patch("app.middleware.session_refresh.remaining_ttl", new=AsyncMock(return_value=60)), \
         patch("app.middleware.session_refresh.resolve_session", new=AsyncMock(return_value="u1")), \
         patch("app.middleware.session_refresh.create_session", new=AsyncMock(return_value="new-sid")), \
         patch("app.middleware.session_refresh.expire_session", new=AsyncMock()) as expired:
        client = TestClient(_app())
        r = client.get("/api/v1/ping", cookies={settings.SESSION_COOKIE_NAME: "old-sid"})
    set_cookie = r.headers.get("set-cookie", "")
    assert "new-sid" in set_cookie
    assert "HttpOnly" in set_cookie and "SameSite=Lax" in set_cookie
    assert "Secure" in set_cookie and "Path=/" in set_cookie
    assert f"Max-Age={settings.SESSION_TTL_MINUTES * 60}" in set_cookie
    # Old sid is given a short grace instead of being deleted immediately, so
    # a sibling request already in flight for the old sid doesn't 401.
    expired.assert_awaited_once_with("old-sid", settings.SESSION_ROTATE_GRACE_SECONDS)


def test_fresh_session_not_rotated():
    huge = settings.SESSION_TTL_MINUTES * 60
    with patch("app.middleware.session_refresh.remaining_ttl", new=AsyncMock(return_value=huge)), \
         patch("app.middleware.session_refresh.create_session", new=AsyncMock()) as created:
        client = TestClient(_app())
        r = client.get("/api/v1/ping", cookies={settings.SESSION_COOKIE_NAME: "old-sid"})
    created.assert_not_awaited()
    assert "set-cookie" not in {k.lower() for k in r.headers}


def test_no_cookie_no_rotation():
    with patch("app.middleware.session_refresh.remaining_ttl", new=AsyncMock()) as ttl:
        client = TestClient(_app())
        client.get("/api/v1/ping")
    ttl.assert_not_awaited()
