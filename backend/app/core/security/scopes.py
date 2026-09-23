"""Role to scope mapping — the RBAC source of truth.

Replaces the Keycloak realm composite roles. Each role grants a fixed set of
backend scopes; access tokens carry the flattened scope list and every
protected route asserts the scopes it needs via `require_scope`.
"""
from __future__ import annotations

Role = str  # "user" | "staff" | "admin"

ROLES: tuple[str, ...] = ("user", "staff", "admin")

_USER_SCOPES: frozenset[str] = frozenset({
    "agency:list",
    "conversation:read:own",
    "conversation:write:own",
    "message:rate",
})

_STAFF_SCOPES: frozenset[str] = _USER_SCOPES | {
    "dashboard:read",
    "executive:read",
    "health:read",
    "usage:read",
    "feedback:read",
}

_ADMIN_SCOPES: frozenset[str] = _STAFF_SCOPES | {
    "agency:read",
    "agency:write",
    "conversation:read:all",
    "executive:write",
    "analytics:read",
    "feedback:read:detail",
    "audit:read",
    "connlog:read",
    "llm:read",
    "llm:write",
    "settings:read",
    "settings:write",
    "popular:read",
    "popular:write",
    "user:manage",
}

ROLE_SCOPES: dict[str, frozenset[str]] = {
    "user": _USER_SCOPES,
    "staff": _STAFF_SCOPES,
    "admin": _ADMIN_SCOPES,
}


def scopes_for_role(role: str) -> frozenset[str]:
    """The scopes granted to a role; an unknown role gets the base user set."""
    return ROLE_SCOPES.get(role, _USER_SCOPES)
