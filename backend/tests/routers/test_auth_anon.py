from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.models.user import User
from app.routers import auth as auth_router


def _app():
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_anon_creates_ephemeral_user_and_cookie(db):
    client = TestClient(_app())
    r = client.post("/api/v1/authentication/anonymous")
    assert r.status_code == 200
    body = r.json()["user"]
    assert body["isEphemeral"] is True
    assert settings.SESSION_COOKIE_NAME in r.headers.get("set-cookie", "")
    u = await User.get(id=body["id"])
    assert u.is_ephemeral is True and u.role == "user"


@pytest.mark.asyncio
async def test_anon_is_idempotent_with_existing_session(db):
    # base_url must be https: AUTH_COOKIE_SECURE=True, so the Secure cookie is
    # only re-sent by the client's cookie jar on subsequent https requests.
    client = TestClient(_app(), base_url="https://testserver")
    r1 = client.post("/api/v1/authentication/anonymous")           # TestClient persists the cookie
    first_id = r1.json()["user"]["id"]
    before = await User.filter(is_ephemeral=True).count()
    r2 = client.post("/api/v1/authentication/anonymous")
    assert r2.json()["user"]["id"] == first_id
    assert await User.filter(is_ephemeral=True).count() == before  # no new row


@pytest.mark.asyncio
async def test_change_password_rejects_anonymous_session(db):
    anon = await User.create(email="anon-y@ephemeral.local", is_ephemeral=True,
                             role="user", hashed_password="!", is_active=True)
    client = TestClient(_app())
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=str(anon.id))):
        r = client.post(
            "/api/v1/authentication/change-password",
            json={"current_password": "anything", "new_password": "newpw12345"},
            cookies={settings.SESSION_COOKIE_NAME: "anon-sid"},
        )
    assert r.status_code == 401
