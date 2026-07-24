"""Pins the exact surface reachable by `user` and anonymous callers.

This test is the safety net for the five-roles-to-two refactor. It must pass
identically before and after. A diff here means the refactor changed someone's
access, which the design explicitly forbids.

It walks the real route table instead of a hand-written path list so a route
nobody remembered is still covered.
"""
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.auth.dependencies import enforce_role_allowlist
from app.auth.security import create_access_token
from app.main import app
from app.models.user import User

# Path params are substituted with this so concrete paths hit the same regexes
# the chokepoint uses at runtime.
_SAMPLE_ID = "abc-123"


def _concrete_paths() -> list[tuple[str, str]]:
    """Every (method, concrete path) pair the app registers, params filled in."""
    pairs: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        for param in route.param_convertors:
            path = path.replace("{" + param + "}", _SAMPLE_ID)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            pairs.append((method, path))
    return sorted(set(pairs))


def _make_request(method: str, path: str) -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


async def _reachable_by(token: str | None) -> set[tuple[str, str]]:
    """The (method, path) set a caller with this token passes the chokepoint for."""
    creds = (
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        if token is not None
        else None
    )
    reachable = set()
    for method, path in _concrete_paths():
        try:
            await enforce_role_allowlist(_make_request(method, path), credentials=creds)
        except HTTPException:
            continue
        reachable.add((method, path))
    return reachable


async def test_anonymous_surface_is_unchanged(db):
    reachable = await _reachable_by(None)
    # Anonymous short-circuits the chokepoint entirely — per-endpoint auth governs
    # it instead. Pinning the full route table here would test nothing, so assert
    # the property that actually matters.
    assert reachable == set(_concrete_paths())


async def test_user_surface_is_exactly_this(db):
    user = await User.create(email="parity-user@x.com", hashed_password="h", role="user")
    token = create_access_token({"sub": str(user.id)})
    reachable = await _reachable_by(token)

    expected_prefixes_and_exact = {
        ("GET", "/api/v1/agencies"),
        ("POST", "/api/v1/chat"),
        ("POST", "/api/v1/chat/stream"),
        ("POST", "/api/v1/responses"),
        ("POST", "/api/v1/conversations"),  # OpenAI create (own/temp)
        ("PATCH", f"/api/v1/messages/{_SAMPLE_ID}/rating"),
        ("GET", "/api/v1/history"),
        ("POST", "/api/v1/history"),
        ("GET", f"/api/v1/history/{_SAMPLE_ID}"),
        ("DELETE", f"/api/v1/history/{_SAMPLE_ID}"),
        # History page expands a conversation; ownership-scoped in the handler.
        ("GET", f"/api/v1/history/{_SAMPLE_ID}/messages"),
        # NOTE: the six read-only ops dashboards (dashboard/stats, executive-summary,
        # agency-health, usage-heatmap, insight/usage, feedback/stats) were moved to
        # `staff`-only in the staff-role split — a plain `user` can no longer reach
        # them. Their staff access is pinned in test_staff_allowlist.py.
    }
    # Every /auth/* route and every public GET is also reachable; enumerate them
    # from the route table so new ones are picked up rather than silently missed.
    auth_routes = {(m, p) for m, p in _concrete_paths() if p.startswith("/api/v1/auth/")}
    public_gets = {
        (m, p)
        for m, p in _concrete_paths()
        if m == "GET" and (p.startswith("/api/v1/public/") or p == "/api/v1/public")
    }
    logo_gets = {
        (m, p)
        for m, p in _concrete_paths()
        if m == "GET" and p == f"/api/v1/agencies/{_SAMPLE_ID}/logo"
    }
    # Routes outside /api/v1/ (currently just GET /health) are NOT reachable: the
    # allowlist predicates only recognize /api/v1/* shapes, so a `user` token is
    # blocked here exactly as it would be on any other unrecognized path.

    expected = expected_prefixes_and_exact | auth_routes | public_gets | logo_gets
    assert reachable == expected


async def test_admin_reaches_the_whole_route_table(db):
    admin = await User.create(email="parity-admin@x.com", hashed_password="h", role="admin")
    token = create_access_token({"sub": str(admin.id)})
    reachable = await _reachable_by(token)
    assert reachable == set(_concrete_paths())


def test_register_route_removed():
    """Self-registration is gone; accounts are admin-created via POST /users."""
    assert ("POST", "/api/v1/auth/register") not in set(_concrete_paths())
