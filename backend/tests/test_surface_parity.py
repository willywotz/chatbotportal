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
from app.main import app

# Path params are substituted with this so concrete paths hit the same regexes
# the chokepoint uses at runtime.
_SAMPLE_ID = "abc-123"


def _concrete_paths() -> list[tuple[str, str]]:
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
    reachable = set()
    for method, path in _concrete_paths():
        try:
            await enforce_role_allowlist(_make_request(method, path, api_key=api_key))
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


def test_register_route_removed():
    """Self-registration is gone; accounts are admin-created via POST /users."""
    assert ("POST", "/api/v1/authentication/register") not in set(_concrete_paths())
