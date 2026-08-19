"""
FastAPI dependencies for authenticated routes.

Usage
-----
    from app.auth.dependencies import get_current_user, require_scope

    @router.get("/protected")
    async def protected(principal = Depends(get_current_user)):
        ...

    @router.get("/scoped")
    async def scoped(principal = Depends(require_scope)):
        ...
"""

from __future__ import annotations

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
