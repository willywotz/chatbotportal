"""Auth router — OIDC bearer authentication.

Endpoints
---------
  GET  /authentication/me   Return the currently authenticated Principal
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security.dependencies import get_current_user
from app.core.security.principal import Principal

router = APIRouter(prefix="/authentication", tags=["Authentication"])


@router.get("/me", summary="Get current authenticated user")
async def me(principal: Principal = Depends(get_current_user)) -> dict:
    return {
        "id": principal.id,
        "email": principal.email,
        "display_name": principal.display_name,
        "role": principal.role,
    }
