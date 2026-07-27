from unittest.mock import AsyncMock, patch

import pytest

from app.auth.ws import resolve_ws_user, ws_origin_allowed
from app.config import settings
from app.models.user import User


class _WS:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}


def test_origin_allowed_matches_cors(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://ok.example"])
    assert ws_origin_allowed(_WS(headers={"origin": "https://ok.example"})) is True
    assert ws_origin_allowed(_WS(headers={"origin": "https://evil.example"})) is False
    assert ws_origin_allowed(_WS()) is False  # missing origin


def test_origin_wildcard_allows_all(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["*"])
    assert ws_origin_allowed(_WS(headers={"origin": "https://anything"})) is True


@pytest.mark.asyncio
async def test_resolve_ws_user_from_cookie(db):
    u = await User.create(email="a@b.co", hashed_password="x", role="user", is_active=True)
    with patch("app.auth.ws.resolve_session", new=AsyncMock(return_value=str(u.id))):
        got = await resolve_ws_user(_WS(cookies={settings.SESSION_COOKIE_NAME: "sid"}))
    assert got.id == u.id


@pytest.mark.asyncio
async def test_resolve_ws_user_bad_header_no_cookie_fallback(db):
    # header present but not a valid api-key -> None, cookie ignored
    with patch("app.auth.ws.resolve_session", new=AsyncMock(return_value="should-not-be-used")):
        got = await resolve_ws_user(_WS(headers={"authorization": "Bearer tcg_bad"},
                                        cookies={settings.SESSION_COOKIE_NAME: "sid"}))
    assert got is None
