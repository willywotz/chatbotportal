"""Pins the exact surface reachable by `user` and anonymous callers.

This test is the safety net for the five-roles-to-two refactor. It must pass
identically before and after. A diff here means the refactor changed someone's
access, which the design explicitly forbids.

It walks the real route table instead of a hand-written path list so a route
nobody remembered is still covered.
"""
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from app.auth.dependencies import enforce_role_allowlist
from app.auth.security import generate_api_key, hash_api_key
from app.main import app
from app.models.user import User, UserAPIKey

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


def _make_request(method: str, path: str, *, api_key: str | None = None) -> Request:
    headers = [(b"authorization", f"Bearer {api_key}".encode())] if api_key else []
    return Request({"type": "http", "method": method, "path": path, "headers": headers})


async def _reachable_by(api_key: str | None) -> set[tuple[str, str]]:
    """The (method, path) set a caller with this API key passes the chokepoint for."""
    reachable = set()
    for method, path in _concrete_paths():
        try:
            await enforce_role_allowlist(_make_request(method, path, api_key=api_key))
        except HTTPException:
            continue
        reachable.add((method, path))
    return reachable


async def _api_key_for(email: str, role: str) -> str:
    user = await User.create(email=email, hashed_password="h", role=role)
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    return raw


async def test_anonymous_surface_is_unchanged(db):
    reachable = await _reachable_by(None)
    # Anonymous short-circuits the chokepoint entirely — per-endpoint auth governs
    # it instead. Pinning the full route table here would test nothing, so assert
    # the property that actually matters.
    assert reachable == set(_concrete_paths())


async def test_user_surface_is_exactly_this(db):
    raw = await _api_key_for("parity-user@x.com", "user")
    reachable = await _reachable_by(raw)

    expected_prefixes_and_exact = {
        ("GET", "/api/v1/agencies"),
        ("POST", "/api/v1/chat"),
        ("POST", "/api/v1/responses"),
        ("GET", f"/api/v1/responses/{_SAMPLE_ID}"),
        ("DELETE", f"/api/v1/responses/{_SAMPLE_ID}"),
        ("GET", f"/api/v1/responses/{_SAMPLE_ID}/input_items"),
        ("POST", f"/api/v1/responses/{_SAMPLE_ID}/cancel"),  # unsupported; 501 stub
        ("POST", "/api/v1/responses/input_tokens"),  # unsupported; 501 stub
        ("POST", "/api/v1/responses/compact"),  # unsupported; 501 stub
        ("POST", "/api/v1/conversations"),  # OpenAI create (own/temp)
        ("GET", f"/api/v1/conversations/{_SAMPLE_ID}"),
        ("POST", f"/api/v1/conversations/{_SAMPLE_ID}"),
        ("DELETE", f"/api/v1/conversations/{_SAMPLE_ID}"),
        ("POST", f"/api/v1/conversations/{_SAMPLE_ID}/items"),
        ("GET", f"/api/v1/conversations/{_SAMPLE_ID}/items"),
        ("GET", f"/api/v1/conversations/{_SAMPLE_ID}/items/{_SAMPLE_ID}"),
        ("DELETE", f"/api/v1/conversations/{_SAMPLE_ID}/items/{_SAMPLE_ID}"),
        ("PATCH", f"/api/v1/messages/{_SAMPLE_ID}/rating"),
        ("GET", "/api/v1/history"),
        ("POST", "/api/v1/history"),
        ("GET", f"/api/v1/history/{_SAMPLE_ID}"),
        ("DELETE", f"/api/v1/history/{_SAMPLE_ID}"),
        # History page expands a conversation; ownership-scoped in the handler.
        ("GET", f"/api/v1/history/{_SAMPLE_ID}/messages"),
        ("POST", "/api/v1/authentication/logout"),
        ("POST", "/api/v1/authentication/anonymous"),
        # NOTE: the six read-only ops dashboards (dashboard/stats, executive-summary,
        # agency-health, usage-heatmap, insight/usage, feedback/stats) were moved to
        # `staff`-only in the staff-role split — a plain `user` can no longer reach
        # them. Their staff access is pinned in test_staff_allowlist.py.
    }
    # Every /auth/* route and every public GET is also reachable; enumerate them
    # from the route table so new ones are picked up rather than silently missed.
    auth_routes = {(m, p) for m, p in _concrete_paths() if p.startswith("/api/v1/authentication/")}
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
    # Agent-proxy is an external OneChat callback with no portal API key; it
    # bypasses the role allowlist for every method (see _AGENT_PROXY_PATTERN).
    agent_proxy_routes = {
        (m, p) for m, p in _concrete_paths() if p.startswith("/api/v1/agent-proxy/")
    }
    # Routes outside /api/v1/ (currently just GET /health) are NOT reachable: the
    # allowlist predicates only recognize /api/v1/* shapes, so a `user` token is
    # blocked here exactly as it would be on any other unrecognized path.

    expected = expected_prefixes_and_exact | auth_routes | public_gets | logo_gets | agent_proxy_routes
    assert reachable == expected


async def test_admin_reaches_the_whole_route_table(db):
    raw = await _api_key_for("parity-admin@x.com", "admin")
    reachable = await _reachable_by(raw)
    assert reachable == set(_concrete_paths())


def test_register_route_removed():
    """Self-registration is gone; accounts are admin-created via POST /users."""
    assert ("POST", "/api/v1/authentication/register") not in set(_concrete_paths())
