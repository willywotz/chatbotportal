"""The basic-user allowlist maps 1:1 to the Chat + Architecture pages."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth.dependencies import _is_allowed_for_basic_user, _resolve_role, enforce_role_allowlist
from app.auth.security import generate_api_key, hash_api_key
from app.config import settings
from app.models.user import User, UserAPIKey


def test_chat_endpoints_allowed():
    assert _is_allowed_for_basic_user("POST", "/api/v1/chat")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/chat")


def test_message_rating_allowed():
    assert _is_allowed_for_basic_user("PATCH", "/api/v1/messages/abc-123/rating")
    assert not _is_allowed_for_basic_user("PATCH", "/api/v1/messages/abc-123/rating/extra")


def test_agencies_list_allowed_but_not_mutations():
    assert _is_allowed_for_basic_user("GET", "/api/v1/agencies")
    assert not _is_allowed_for_basic_user("DELETE", "/api/v1/agencies/abc-123")
    assert not _is_allowed_for_basic_user("PATCH", "/api/v1/agencies/abc-123/status")


def test_own_conversations_allowed():
    assert _is_allowed_for_basic_user("GET", "/api/v1/history")
    assert _is_allowed_for_basic_user("DELETE", "/api/v1/history/abc-123")


def test_own_conversation_messages_readable():
    """The History page reads this sub-resource; the handler scopes it to the owner."""
    assert _is_allowed_for_basic_user("GET", "/api/v1/history/abc-123/messages")


def test_conversation_messages_is_read_only():
    """Only GET is granted, so a future write verb on this path stays admin-only."""
    assert not _is_allowed_for_basic_user("POST", "/api/v1/history/abc-123/messages")
    assert not _is_allowed_for_basic_user("DELETE", "/api/v1/history/abc-123/messages")


def test_auth_self_endpoints_allowed():
    assert _is_allowed_for_basic_user("GET", "/api/v1/auth/me")
    assert _is_allowed_for_basic_user("POST", "/api/v1/auth/login")


def test_restricted_pages_blocked():
    assert not _is_allowed_for_basic_user("GET", "/api/v1/connection-logs")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/api-keys/")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/analytics-insights")
    assert not _is_allowed_for_basic_user(
        "GET", "/api/v1/agencies/abc-123/health/history"
    )
    assert not _is_allowed_for_basic_user(
        "GET", "/api/v1/feedback/agencies/abc-123/low-rated"
    )


def test_ops_dashboard_reads_denied_for_basic_user():
    """The six read-only dashboards are now staff-only, not basic-user."""
    assert not _is_allowed_for_basic_user("GET", "/api/v1/dashboard/stats")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/executive-summary")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/agency-health")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/usage-heatmap")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/insight/usage")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/feedback/stats")


def test_executive_summary_regenerate_still_admin_only():
    assert not _is_allowed_for_basic_user(
        "POST", "/api/v1/executive-summary/regenerate"
    )


def _request(method: str, path: str, *, api_key: str | None = None,
             session_id: str | None = None) -> Request:
    headers = []
    if api_key is not None:
        headers.append((b"authorization", f"Bearer {api_key}".encode()))
    if session_id is not None:
        headers.append((b"cookie", f"{settings.SESSION_COOKIE_NAME}={session_id}".encode()))
    return Request(
        {"type": "http", "method": method, "path": path,
         "headers": headers, "query_string": b""}
    )


async def _api_key_for(email: str, role: str) -> str:
    user = await User.create(email=email, hashed_password="h", role=role)
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    return raw


async def test_resolve_role_from_api_key(db):
    raw = await _api_key_for("role-key@x.com", "user")
    assert await _resolve_role(_request("GET", "/x", api_key=raw)) == "user"


async def test_resolve_role_admin(db):
    raw = await _api_key_for("role-admin@x.com", "admin")
    assert await _resolve_role(_request("GET", "/x", api_key=raw)) == "admin"


async def test_resolve_role_from_session_cookie(db):
    user = await User.create(email="role-session@x.com", hashed_password="h", role="user")
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=str(user.id))):
        role = await _resolve_role(_request("GET", "/x", session_id="sid-1"))
    assert role == "user"


async def test_resolve_role_invalid_returns_none(db):
    assert await _resolve_role(_request("GET", "/x")) is None
    assert await _resolve_role(_request("GET", "/x", api_key="tcg_bogus")) is None


async def test_resolve_role_inactive_user_returns_none(db):
    raw = await _api_key_for("role-inactive-user@x.com", "user")
    await User.filter(email="role-inactive-user@x.com").update(is_active=False)
    assert await _resolve_role(_request("GET", "/x", api_key=raw)) is None


async def test_resolve_role_unusable_api_key_returns_none(db):
    from app.utils import now

    user = await User.create(email="role-revoked@x.com", hashed_password="h", role="user")
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id,
        name="n",
        key_hash=hash_api_key(raw),
        key_prefix=raw[:12],
        revoked_at=now(),
    )
    assert await _resolve_role(_request("GET", "/x", api_key=raw)) is None


async def test_basic_user_blocked_on_restricted_page(db):
    raw = await _api_key_for("b1@x.com", "user")
    with pytest.raises(HTTPException) as e:
        await enforce_role_allowlist(_request("GET", "/api/v1/connection-logs", api_key=raw))
    assert e.value.status_code == 403


async def test_basic_user_allowed_on_chat(db):
    raw = await _api_key_for("b2@x.com", "user")
    # No raise == allowed.
    assert await enforce_role_allowlist(_request("POST", "/api/v1/chat", api_key=raw)) is None


async def test_basic_user_denied_on_dashboard_stats(db):
    """Dashboards moved to the staff allowlist; a plain user no longer reaches them."""
    raw = await _api_key_for("b4@x.com", "user")
    with pytest.raises(HTTPException) as e:
        await enforce_role_allowlist(_request("GET", "/api/v1/dashboard/stats", api_key=raw))
    assert e.value.status_code == 403


async def test_basic_user_blocked_on_regenerate(db):
    raw = await _api_key_for("b5@x.com", "user")
    with pytest.raises(HTTPException) as e:
        await enforce_role_allowlist(
            _request("POST", "/api/v1/executive-summary/regenerate", api_key=raw)
        )
    assert e.value.status_code == 403


async def test_admin_unaffected(db):
    raw = await _api_key_for("b3@x.com", "admin")
    assert await enforce_role_allowlist(_request("GET", "/api/v1/dashboard/stats", api_key=raw)) is None


async def test_anonymous_unaffected(db):
    assert await enforce_role_allowlist(_request("GET", "/api/v1/dashboard/stats")) is None
