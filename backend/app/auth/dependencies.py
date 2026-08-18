"""
FastAPI dependencies for authenticated routes.

Usage
-----
    from app.auth.dependencies import get_current_user, require_admin

    @router.get("/protected")
    async def protected(principal = Depends(get_current_user)):
        ...

    @router.get("/admin-only")
    async def admin_only(principal = Depends(require_admin)):
        ...
"""

from __future__ import annotations

import re

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import SecurityScopes
from starlette.requests import HTTPConnection

from app.auth.keycloak import InvalidToken, Principal, verify_token
from app.services.usage_context import current_user_id

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
    "/api/v1/dashboard/statistics",
    "/api/v1/executive-summary",
    "/api/v1/agency-health",
    "/api/v1/usage-heatmap",
    "/api/v1/insight/usage",
    "/api/v1/feedback/statistics",
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

    Chat, message rating, own-history management, and the self/auth endpoints.
    Everything else is a privileged write.
    """
    if path.startswith("/api/v1/authentication/"):  # all auth endpoints — each guards itself internally
        return True
    if method == "POST" and path == "/api/v1/chat":
        return True
    if method == "PATCH" and _MESSAGE_RATING_PATH.match(path):
        return True
    if _HISTORY_PATH.match(path):  # all verbs: manage own history
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


def _bearer(conn: HTTPConnection) -> str | None:
    auth = conn.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else None


def _principal(conn: HTTPConnection) -> Principal | None:
    token = _bearer(conn)
    if token is None:
        return None
    try:
        p = verify_token(token)
    except InvalidToken:
        raise _invalid_credentials
    current_user_id.set(p.id)
    return p


async def get_current_user_optional(request: Request) -> Principal | None:
    return _principal(request)


async def get_current_user(request: Request) -> Principal:
    p = _principal(request)
    if p is None:
        raise _invalid_credentials
    return p


async def get_current_user_non_ephemeral(
    principal: Principal = Depends(get_current_user),
) -> Principal:
    return principal


async def require_admin(principal: Principal = Depends(get_current_user)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return principal


async def require_scope(
    security_scopes: SecurityScopes,
    principal: Principal = Depends(get_current_user),
) -> Principal:
    # Resolve via Depends(get_current_user) — NOT a direct call — so that
    # app.dependency_overrides[get_current_user] in tests continues to control
    # this route's identity. A direct call would bypass the override.
    missing = set(security_scopes.scopes) - principal.scopes
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This token lacks the required scope",
        )
    return principal


async def _resolve_role(conn: HTTPConnection) -> str | None:
    """Role only, no side effects. Fail-open: a bad token resolves to None so
    the allowlist passes through and the endpoint's own auth decides (see
    ``enforce_role_allowlist``). Unlike ``get_current_user*``, this path never
    raises."""
    token = _bearer(conn)
    if token is None:
        return None
    try:
        p = verify_token(token)
    except InvalidToken:
        return None
    return p.role


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
        return  # WebSocket routes enforce their own auth
    method = conn.scope["method"]
    path = conn.scope["path"]
    if _is_public_get(method, path):
        return
    if path.startswith("/api/v1/public/"):
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
