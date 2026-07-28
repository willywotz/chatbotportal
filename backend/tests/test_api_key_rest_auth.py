"""REST endpoints accept tcg_ API keys as bearer tokens or a session cookie."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.auth.security import generate_api_key, hash_api_key
from app.config import settings
from app.models.user import User, UserAPIKey


def _request(*, api_key: str | None = None, session_id: str | None = None) -> Request:
    headers = []
    if api_key is not None:
        headers.append((b"authorization", f"Bearer {api_key}".encode()))
    if session_id is not None:
        headers.append((b"cookie", f"{settings.SESSION_COOKIE_NAME}={session_id}".encode()))
    return Request(
        {"type": "http", "method": "GET", "path": "/x", "headers": headers, "query_string": b""}
    )


async def _user_with_key(email: str, *, is_active: bool = True):
    user = await User.create(email=email, hashed_password="h", is_active=is_active)
    raw = generate_api_key()
    key = await UserAPIKey.create(
        user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    return user, raw, key


async def test_api_key_authenticates_rest(db):
    user, raw, _ = await _user_with_key("k@x.com")
    result = await get_current_user(_request(api_key=raw))
    assert result.id == user.id


async def test_api_key_stamps_last_used(db):
    _, raw, key = await _user_with_key("k2@x.com")
    assert key.last_used_at is None
    await get_current_user(_request(api_key=raw))
    refreshed = await UserAPIKey.get(id=key.id)
    assert refreshed.last_used_at is not None


async def test_session_cookie_still_works(db):
    user = await User.create(email="j@x.com", hashed_password="h")
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=str(user.id))):
        result = await get_current_user(_request(session_id="sid-1"))
    assert result.id == user.id


async def test_invalid_token_required_raises_401(db):
    with pytest.raises(HTTPException) as e:
        await get_current_user(_request(api_key="tcg_bogus-key-value"))
    assert e.value.status_code == 401


async def test_inactive_user_key_rejected(db):
    _, raw, _ = await _user_with_key("i@x.com", is_active=False)
    with pytest.raises(HTTPException) as e:
        await get_current_user(_request(api_key=raw))
    assert e.value.status_code == 401


async def test_optional_no_credentials_is_anonymous(db):
    assert await get_current_user_optional(_request()) is None


async def test_optional_valid_key_resolves(db):
    user, raw, _ = await _user_with_key("o@x.com")
    result = await get_current_user_optional(_request(api_key=raw))
    assert result is not None and result.id == user.id


async def test_optional_invalid_api_key_raises_401(db):
    # Footgun fix: a deliberate (tcg_) API-key auth that fails is rejected, not
    # silently treated as anonymous (which would bypass rate limits / quotas).
    with pytest.raises(HTTPException) as e:
        await get_current_user_optional(_request(api_key="tcg_nope"))
    assert e.value.status_code == 401


async def test_optional_non_api_key_bearer_401s(db):
    # JWT is gone: Authorization: Bearer now means "this is an API key". A
    # non-tcg_-prefixed bearer value is a deliberate but unrecognized
    # credential, so it 401s rather than degrading to anonymous.
    with pytest.raises(HTTPException) as e:
        await get_current_user_optional(_request(api_key="not-an-api-key"))
    assert e.value.status_code == 401


async def test_optional_missing_session_degrades_to_anonymous(db):
    # A missing/expired session cookie is the browser-auto-attach case that
    # must degrade to anonymous so optional-auth endpoints (e.g. chat) work.
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=None)):
        assert await get_current_user_optional(_request(session_id="dead")) is None


async def test_resolve_sets_context_for_api_key(db):
    from app.auth.dependencies import _resolve_token
    from app.services.usage_context import current_api_key_id, current_user_id

    user, raw, key = await _user_with_key("ctx@x.com")
    resolved = await _resolve_token(raw)

    assert resolved.id == user.id
    assert current_user_id.get() == user.id
    assert current_api_key_id.get() == key.id


async def test_resolve_session_user_sets_user_only(db):
    from app.auth.dependencies import _resolve_session_user
    from app.services.usage_context import current_api_key_id, current_user_id

    current_api_key_id.set(None)
    user = await User.create(email="sess@x.com", hashed_password="h", is_active=True)
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=str(user.id))):
        resolved = await _resolve_session_user("sid-1")

    assert resolved.id == user.id
    assert current_user_id.get() == user.id
    assert current_api_key_id.get() is None
