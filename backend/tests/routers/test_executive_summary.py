"""Tests for the executive-summary regenerate endpoint (admin-gated, force regen)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _find_route(path: str, method: str):
    from app.routers import executive_summary

    for route in executive_summary.router.routes:
        if route.path == path and method in route.methods:
            return route
    raise AssertionError(f"route {method} {path} not found")


def test_regenerate_route_requires_admin():
    from app.auth.dependencies import require_admin

    route = _find_route("/executive-summary/regenerate", "POST")
    calls = [d.call for d in route.dependant.dependencies]
    assert require_admin in calls, "regenerate endpoint is not gated by require_admin"


def test_get_route_is_not_admin_gated():
    from app.auth.dependencies import require_admin

    route = _find_route("/executive-summary", "GET")
    calls = [d.call for d in route.dependant.dependencies]
    assert require_admin not in calls


@pytest.mark.asyncio
async def test_regenerate_endpoint_returns_new_brief():
    from app.routers import executive_summary as router_module

    brief = MagicMock()
    brief.content = "fresh brief"
    brief.status = "ok"
    brief.generated_at = "2026-06-11T00:00:00+07:00"

    with patch.object(router_module, "regenerate_weekly_brief", new=AsyncMock(return_value=brief)):
        result = await router_module.regenerate_executive_summary_endpoint()

    assert result["weeklyBrief"] == "fresh brief"
    assert result["status"] == "ok"
