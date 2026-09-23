"""Role to scope mapping mirrors the retired Keycloak realm composites."""
from __future__ import annotations

from app.core.security.scopes import ROLE_SCOPES, scopes_for_role

_EXPECTED_USER = {
    "agency:list", "conversation:read:own", "conversation:write:own", "message:rate",
}
_EXPECTED_STAFF = _EXPECTED_USER | {
    "dashboard:read", "executive:read", "health:read", "usage:read", "feedback:read",
}
_EXPECTED_ADMIN = _EXPECTED_STAFF | {
    "agency:read", "agency:write", "conversation:read:all", "executive:write",
    "analytics:read", "feedback:read:detail", "audit:read", "connlog:read",
    "llm:read", "llm:write", "settings:read", "settings:write", "popular:read",
    "popular:write", "user:manage",
}


def test_user_scopes_exact():
    assert set(ROLE_SCOPES["user"]) == _EXPECTED_USER


def test_staff_scopes_exact():
    assert set(ROLE_SCOPES["staff"]) == _EXPECTED_STAFF


def test_admin_scopes_exact():
    assert set(ROLE_SCOPES["admin"]) == _EXPECTED_ADMIN


def test_roles_are_nested():
    assert ROLE_SCOPES["user"] < ROLE_SCOPES["staff"] < ROLE_SCOPES["admin"]


def test_unknown_role_falls_back_to_user():
    assert scopes_for_role("nope") == ROLE_SCOPES["user"]
