"""
FastAPI dependencies for authenticated routes.

Usage
-----
    from app.auth.dependencies import get_current_user, require_admin

    @router.get("/protected")
    async def protected(user = Depends(get_current_user)):
        ...

    @router.get("/admin-only")
    async def admin_only(user = Depends(require_admin)):
        ...
"""

from __future__ import annotations

import re

from fastapi import Depends, HTTPException, Request, status
from starlette.requests import HTTPConnection

from app.auth.security import API_KEY_PREFIX, hash_api_key
from app.config import settings
from app.models.user import User, UserAPIKey
from app.services.auth_session import resolve_session
from app.services.usage_context import current_api_key_id, current_user_id
from app.utils import now

_invalid_credentials = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

_MESSAGE_RATING_PATH = re.compile(r"^/api/v1/messages/[^/]+/rating$")
# Matches the collection and /{id} only. The /{id}/messages sub-resource is granted
# separately and GET-only (see below), so adding a write verb there would not inherit access.
_HISTORY_PATH = re.compile(r"^/api/v1/history(?:/[^/]+)?$")
# The History page reads this to expand a conversation. Safe to grant because the
# handler applies the same own-or-admin ownership check as GET /history/{id}.
_HISTORY_MESSAGES_GET_PATTERN = re.compile(r"^/api/v1/history/[^/]+/messages$")
# Covers create, /{id}, and the /{id}/items* sub-resources. Safe for all verbs: every
# OpenAI conversations endpoint applies its own owns() check (404s a non-owner).
_OAI_CONVERSATION_PATH = re.compile(r"^/api/v1/conversations(?:/.*)?$")
# Covers create plus the retrieve/delete/input_items/cancel/input_tokens/compact
# sub-resources. Safe for all verbs: every /responses/{id} endpoint owner-checks,
# and the rest are create or unsupported (501) stubs.
_RESPONSES_PATH = re.compile(r"^/api/v1/responses(?:/.*)?$")

_PUBLIC_PREFIX = "/api/v1/public"
# Agency logo images are already publicly exposed via GET /public/agencies;
# serving them at /agencies/{id}/logo (not under /public/) keeps the URL an
# <img> tag hits stable, but it must still bypass the role allowlist so an
# authenticated user's attached credential doesn't 403 the fetch.
_AGENCY_LOGO_GET_PATTERN = re.compile(r"^/api/v1/agencies/[^/]+/logo$")

# Agent-proxy is an external OneChat callback, not a portal-user request. It
# carries no portal API key, so it must bypass the role allowlist for every
# method — the same "no portal-role auth" contract the Go agent-proxy had.
_AGENT_PROXY_PATTERN = re.compile(r"^/api/v1/agent-proxy/[^/]+$")

# Read-only ops dashboards a `staff` role may view: Dashboard, Executive,
# Agency Health, Usage Heatmap, Usage Analytics, Feedback. The write side of
# each page (e.g. POST /executive-summary/regenerate) stays admin-only, and a
# plain `user` cannot reach these at all.
_STAFF_GET_EXACT = frozenset({
    "/api/v1/dashboard/stats",
    "/api/v1/executive-summary",
    "/api/v1/agency-health",
    "/api/v1/usage-heatmap",
    "/api/v1/insight/usage",
    "/api/v1/feedback/stats",
})


def _is_public_get(method: str, path: str) -> bool:
    """Anything under ``/api/v1/public/`` is a public GET by definition.

    A logged-in caller's role must never gate an endpoint that an anonymous
    caller can already reach — see ``app/routers/public_status.py`` and
    ``app/routers/popular_questions.py`` (both mounted under this prefix).
    """
    if method != "GET":
        return False
    return (
        path == _PUBLIC_PREFIX
        or path.startswith(_PUBLIC_PREFIX + "/")
        or bool(_AGENCY_LOGO_GET_PATTERN.match(path))
    )


def _is_shared_write(method: str, path: str) -> bool:
    """Writes every authenticated role (incl. read-only ones) may perform.

    Chat (including the OpenAI-compatible /responses surface), message rating,
    own-history management, and the self/auth endpoints. Everything else is
    a privileged write.
    """
    if path.startswith("/api/v1/authentication/"):  # all auth endpoints — each guards itself internally
        return True
    if method == "POST" and path == "/api/v1/chat":
        return True
    if method == "PATCH" and _MESSAGE_RATING_PATH.match(path):
        return True
    if _HISTORY_PATH.match(path):  # all verbs: manage own history
        return True
    if _OAI_CONVERSATION_PATH.match(path):  # OpenAI conversations + items; each endpoint owner-checks
        return True
    if _RESPONSES_PATH.match(path):  # OpenAI responses + sub-resources; each endpoint owner-checks
        return True
    return False


def _is_allowed_for_basic_user(method: str, path: str) -> bool:
    """A plain ``user`` role: chat + architecture list + own history + shared writes."""
    if _is_shared_write(method, path):
        return True
    if method == "GET" and path == "/api/v1/agencies":  # Architecture page (list only)
        return True
    if method == "GET" and _HISTORY_MESSAGES_GET_PATTERN.match(path):
        return True
    return False


def _is_allowed_for_staff(method: str, path: str) -> bool:
    """Role ``staff``: everything a basic user can do, plus read-only ops dashboards."""
    if _is_allowed_for_basic_user(method, path):
        return True
    return method == "GET" and path in _STAFF_GET_EXACT


def _header_api_key(conn: HTTPConnection) -> str | None:
    auth = conn.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else None


async def _resolve_api_key(token: str) -> User | None:
    """API-key path only (JWT is gone). Stamps last_used + usage context."""
    if not token.startswith(API_KEY_PREFIX):
        return None
    api_key = await UserAPIKey.filter(key_hash=hash_api_key(token)).first()
    if api_key is None or not api_key.is_usable():
        return None
    user = await User.filter(id=api_key.user_id, is_active=True).first()
    if user is None:
        return None
    api_key.last_used_at = now()
    await api_key.save(update_fields=["last_used_at"])
    current_user_id.set(user.id)
    current_api_key_id.set(api_key.id)
    return user


# Both WS handlers now go through resolve_ws_user (app/auth/ws.py) instead.
# Kept only for compatibility with tests/auth/test_session_cookie_auth.py and
# tests/test_api_key_rest_auth.py, which reference this alias directly.
_resolve_token = _resolve_api_key


async def _resolve_session_user(session_id: str) -> User | None:
    user_id = await resolve_session(session_id)
    if not user_id:
        return None
    user = await User.filter(id=user_id, is_active=True).first()
    if user is not None:
        current_user_id.set(user.id)
    return user


async def get_current_user_optional(request: Request) -> User | None:
    key = _header_api_key(request)
    if key is not None:
        user = await _resolve_api_key(key)
        if user is None:  # deliberate API key that fails must 401
            raise _invalid_credentials
        return user
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        return await _resolve_session_user(sid)  # bad session -> None (anonymous)
    return None


async def get_current_user(request: Request) -> User:
    key = _header_api_key(request)
    if key is not None:  # header present => header decides, no cookie fallback
        user = await _resolve_api_key(key)
        if user is None:
            raise _invalid_credentials
        return user
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        user = await _resolve_session_user(sid)
        if user is not None:
            return user
    raise _invalid_credentials


async def get_current_user_non_ephemeral(
    user: User = Depends(get_current_user),
) -> User:
    """Real accounts / API keys only — anonymous (ephemeral) sessions are refused.

    The OpenAI-compatible surfaces are not for auto-created anonymous identities.
    """
    if user.is_ephemeral:
        raise _invalid_credentials
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user


async def _resolve_role(conn: HTTPConnection) -> str | None:
    """Role only, no side effects (no last_used stamp / rate charge)."""
    key = _header_api_key(conn)
    if key is not None:
        if not key.startswith(API_KEY_PREFIX):
            return None
        api_key = await UserAPIKey.filter(key_hash=hash_api_key(key)).first()
        if api_key is None or not api_key.is_usable():
            return None
        user = await User.filter(id=api_key.user_id, is_active=True).first()
        return user.role if user else None
    sid = conn.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        user_id = await resolve_session(sid)
        if user_id:
            user = await User.filter(id=user_id, is_active=True).first()
            return user.role if user else None
    return None


_ROLE_ALLOWLIST = {
    "user": _is_allowed_for_basic_user,
    "staff": _is_allowed_for_staff,
}


async def enforce_role_allowlist(conn: HTTPConnection) -> None:
    """Deny-by-default chokepoint for every role except ``admin``.

    Anonymous callers pass straight through; their access is governed by each
    endpoint's own auth. Wired as a global dependency in ``app.main`` so it
    runs once per request.
    """
    if conn.scope["type"] != "http":
        return  # WebSocket routes enforce their own auth (see app/auth/ws.py)
    method = conn.scope["method"]
    path = conn.scope["path"]
    if _is_public_get(method, path):
        return
    if _AGENT_PROXY_PATTERN.match(path):
        return
    role = await _resolve_role(conn)
    # An unresolvable credential (missing/invalid/expired/inactive) passes
    # through so the endpoint's own auth returns 401 rather than a misleading
    # 403. `admin` is governed per-endpoint. Every other role — including rows
    # left behind by a not-yet-run migration — is denied by default.
    if role is None or role == "admin":
        return
    check = _ROLE_ALLOWLIST.get(role, _is_allowed_for_basic_user)
    if not check(method, path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This role does not have access to this resource",
        )
