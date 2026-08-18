"""The basic-user allowlist maps 1:1 to the Chat + Architecture pages.

Only direct-predicate tests live here — no real api-key/session transport
(that's the removed auth scheme; see tests/auth/test_dependencies_token.py
for the token-based paths).
"""
from starlette.requests import Request

from app.auth.dependencies import _is_allowed_for_basic_user, _resolve_role, enforce_role_allowlist


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
    assert _is_allowed_for_basic_user("GET", "/api/v1/history/abc-123/messages")


def test_conversation_messages_is_read_only():
    """Only GET is granted, so a future write verb on this path stays admin-only."""
    assert not _is_allowed_for_basic_user("POST", "/api/v1/history/abc-123/messages")
    assert not _is_allowed_for_basic_user("DELETE", "/api/v1/history/abc-123/messages")


def test_auth_self_endpoints_allowed():
    assert _is_allowed_for_basic_user("GET", "/api/v1/authentication/me")
    assert _is_allowed_for_basic_user("POST", "/api/v1/authentication/login")


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
    assert not _is_allowed_for_basic_user("GET", "/api/v1/dashboard/statistics")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/executive-summary")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/agency-health")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/usage-heatmap")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/insight/usage")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/feedback/statistics")


def test_executive_summary_regenerate_still_admin_only():
    assert not _is_allowed_for_basic_user(
        "POST", "/api/v1/executive-summary/regenerate"
    )


def _request(method: str, path: str, *, api_key: str | None = None) -> Request:
    headers = []
    if api_key is not None:
        headers.append((b"authorization", f"Bearer {api_key}".encode()))
    return Request(
        {"type": "http", "method": method, "path": path,
         "headers": headers, "query_string": b""}
    )


async def test_resolve_role_invalid_returns_none(db):
    assert await _resolve_role(_request("GET", "/x")) is None
    assert await _resolve_role(_request("GET", "/x", api_key="tcg_bogus")) is None


async def test_anonymous_unaffected(db):
    assert await enforce_role_allowlist(_request("GET", "/api/v1/dashboard/statistics")) is None
