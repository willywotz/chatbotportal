"""There is no global auth gate: access is per-route `require_scope` only.

Confirms the three shapes that used to be mediated by the deleted role
allowlist: a scoped route with a matching scope (200), a public route with
no credential at all (200), and a scoped route with no credential (401 from
`require_scope`'s own `get_current_user` dependency, not a global chokepoint).
"""
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_scoped_route_reachable_with_matching_scope(as_principal):
    as_principal(role="staff", scopes=["dashboard:read"])
    from app.routers import dashboard as router_module
    with patch.object(router_module, "get_dashboard_stats", new=AsyncMock(return_value={})):
        async with await _client() as c:
            r = await c.get("/api/v1/dashboard/statistics")
    assert r.status_code == 200


async def test_public_route_reachable_with_no_token(db):
    async with await _client() as c:
        r = await c.get("/api/v1/public/status")
    assert r.status_code == 200


async def test_scoped_route_rejects_no_token():
    async with await _client() as c:
        r = await c.get("/api/v1/audit-log/")
    assert r.status_code == 401
