"""
Auth router — session-cookie-based authentication.

Accounts are created by an admin via ``POST /api/v1/users``; there is no
public self-registration.

Endpoints
---------
  POST  /auth/login             Sign in → sets session cookie
  POST  /auth/logout            End the current session
  GET   /auth/me                Return the currently authenticated user
  PATCH /auth/me                Update display_name / avatar_url
  POST  /auth/change-password   Change your own password
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from app.auth.dependencies import get_current_user, get_current_user_non_ephemeral
from app.config import settings
from app.models.user import User
from pydantic import BaseModel, EmailStr

from app.auth.security import verify_password
from app.services.auth_session import create_session, delete_session
from app.services.user import hash_new_password

router = APIRouter(prefix="/auth", tags=["Auth"])

_UNUSABLE_PASSWORD = "!"  # anon users never authenticate with a password


# ---------------------------------------------------------------------------
# Pydantic schemas (defined inline — small enough not to need a separate file)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name or user.email.split("@")[0],
        "role": user.role,
        "avatarUrl": user.avatar_url,
        "isEphemeral": user.is_ephemeral,
    }


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", summary="Sign in and start a session")
async def login(body: LoginRequest, response: Response) -> dict:
    user = await User.filter(email=body.email, is_active=True).first()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง",
        )

    session_id = await create_session(str(user.id))
    response.set_cookie(
        settings.SESSION_COOKIE_NAME, session_id,
        httponly=True, secure=settings.AUTH_COOKIE_SECURE, samesite="Lax",
        max_age=settings.SESSION_TTL_MINUTES * 60, path="/",
    )
    return {"user": _user_dict(user)}


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout", summary="End the current session")
async def logout(request: Request, response: Response) -> dict:
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        await delete_session(sid)
    response.delete_cookie(
        settings.SESSION_COOKIE_NAME, path="/",
        httponly=True, secure=settings.AUTH_COOKIE_SECURE, samesite="Lax",
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Anonymous session bootstrap
# ---------------------------------------------------------------------------

@router.post("/anon", summary="Start an anonymous session (idempotent)")
async def anon(request: Request, response: Response) -> dict:
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        from app.services.auth_session import resolve_session
        user_id = await resolve_session(sid)
        if user_id:
            user = await User.filter(id=user_id, is_active=True).first()
            if user:
                return {"user": _user_dict(user)}
    user = await User.create(
        email=f"anon-{uuid4().hex}@ephemeral.local",
        is_ephemeral=True, role="user", hashed_password=_UNUSABLE_PASSWORD,
    )
    session_id = await create_session(str(user.id))
    response.set_cookie(
        settings.SESSION_COOKIE_NAME, session_id, httponly=True,
        secure=settings.AUTH_COOKIE_SECURE, samesite="Lax",
        max_age=settings.SESSION_TTL_MINUTES * 60, path="/",
    )
    return {"user": _user_dict(user)}


# ---------------------------------------------------------------------------
# Me — get current user
# ---------------------------------------------------------------------------

@router.get("/me", summary="Get current authenticated user")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {"user": _user_dict(user)}


# ---------------------------------------------------------------------------
# Update profile
# ---------------------------------------------------------------------------

@router.patch("/me", summary="Update display name or avatar")
async def update_me(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user_non_ephemeral),
) -> dict:
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.avatar_url is not None:
        user.avatar_url = body.avatar_url
    await user.save()
    return {"user": _user_dict(user)}


# ---------------------------------------------------------------------------
# Change own password
# ---------------------------------------------------------------------------

@router.post("/change-password", summary="Change your own password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user_non_ephemeral),
) -> dict:
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="รหัสผ่านปัจจุบันไม่ถูกต้อง")

    user.hashed_password = hash_new_password(body.new_password)
    await user.save(update_fields=["hashed_password"])
    return {"message": "เปลี่ยนรหัสผ่านสำเร็จ"}
