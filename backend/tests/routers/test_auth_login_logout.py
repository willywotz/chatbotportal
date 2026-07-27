import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.models.user import User
from app.routers import auth as auth_router
from app.services.user import hash_new_password


def _app():
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_login_sets_cookie_and_omits_token(db):
    await User.create(email="a@b.co", hashed_password=hash_new_password("pw12345"),
                      role="admin", is_active=True)
    client = TestClient(_app())
    r = client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "pw12345"})
    assert r.status_code == 200
    assert "access_token" not in r.json()
    assert r.json()["user"]["email"] == "a@b.co"
    set_cookie = r.headers["set-cookie"]
    assert settings.SESSION_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie and "SameSite=Lax" in set_cookie


@pytest.mark.asyncio
async def test_logout_clears_cookie(db):
    await User.create(email="a@b.co", hashed_password=hash_new_password("pw12345"),
                      role="admin", is_active=True)
    client = TestClient(_app())
    client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "pw12345"})
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    # Deletion is a Set-Cookie with an expiry in the past / Max-Age=0.
    assert settings.SESSION_COOKIE_NAME in r.headers.get("set-cookie", "")
