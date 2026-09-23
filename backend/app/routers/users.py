from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_scope
from app.db import get_db
from app.errors import ApiError, ErrorCode
from app.schemas.user import Role, UserCreate, UserCreateResponse, UserListResponse, UserResponse, UserUpdate
from app.services import user_admin
from app.services.audit import record_audit

router = APIRouter(prefix="/users", tags=["Users"])


def _map_error(exc: user_admin.UserAdminError) -> ApiError:
    if isinstance(exc, user_admin.NotFound):
        return ApiError(ErrorCode.NOT_FOUND, str(exc), status=404)
    code = ErrorCode.CONFLICT if exc.status == 409 else ErrorCode.INVALID_REQUEST
    return ApiError(code, str(exc), status=exc.status if exc.status in (400, 409) else 400)


@router.get("", response_model=UserListResponse, summary="List users")
async def list_users(
    search: str | None = Query(None, description="Search email or display name"),
    role: Role | None = Query(None, description="Filter by role: user | staff | admin"),
    status_filter: Literal["active", "inactive", "all"] = Query(
        "all", alias="status", description="Filter by active status"
    ),
    session: AsyncSession = Depends(get_db),
    admin=Security(require_scope, scopes=["user:manage"]),
) -> UserListResponse:
    is_active = None if status_filter == "all" else (status_filter == "active")
    try:
        rows, total = await user_admin.list_users(session, search=search, role=role, is_active=is_active)
    except user_admin.UserAdminError as exc:
        raise _map_error(exc) from exc
    return UserListResponse(data=rows, total=total)


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED, summary="Create a user")
async def create_user(
    body: UserCreate,
    session: AsyncSession = Depends(get_db),
    admin=Security(require_scope, scopes=["user:manage"]),
) -> dict:
    try:
        new_user = await user_admin.create_user(session, body)
    except user_admin.UserAdminError as exc:
        raise _map_error(exc) from exc
    await record_audit(session, admin, "user.create", object_type="user", object_id=new_user.id, detail={"email": new_user.email, "role": new_user.role})
    return {"user": new_user.model_dump()}


@router.get("/{user_id}", response_model=UserResponse, summary="Get user by ID")
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_db),
    admin=Security(require_scope, scopes=["user:manage"]),
) -> UserResponse:
    try:
        return await user_admin.get_user(session, user_id)
    except user_admin.UserAdminError as exc:
        raise _map_error(exc) from exc


@router.patch("/{user_id}", response_model=UserResponse, summary="Update a user")
async def update_user(
    user_id: str,
    body: UserUpdate,
    session: AsyncSession = Depends(get_db),
    admin=Security(require_scope, scopes=["user:manage"]),
) -> UserResponse:
    try:
        user = await user_admin.update_user(session, user_id, body)
    except user_admin.UserAdminError as exc:
        raise _map_error(exc) from exc
    changed = [f for f in ("role", "display_name", "password") if getattr(body, f) is not None]
    if changed:
        await record_audit(
            session, admin, "user.update", object_type="user", object_id=user.id,
            detail={"changed": changed, "role": user.role},
        )
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a user")
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_db),
    admin=Security(require_scope, scopes=["user:manage"]),
) -> None:
    if user_id == admin.id:
        raise ApiError(ErrorCode.FORBIDDEN, "You cannot delete your own account", status=403)
    try:
        await user_admin.delete_user(session, user_id)
    except user_admin.UserAdminError as exc:
        raise _map_error(exc) from exc
    await record_audit(session, admin, "user.delete", object_type="user", object_id=user_id)


@router.post("/{user_id}/deactivate", response_model=UserResponse, summary="Deactivate a user")
async def deactivate_user(
    user_id: str,
    session: AsyncSession = Depends(get_db),
    admin=Security(require_scope, scopes=["user:manage"]),
) -> UserResponse:
    try:
        user = await user_admin.set_enabled(session, user_id, False)
    except user_admin.UserAdminError as exc:
        raise _map_error(exc) from exc
    await record_audit(session, admin, "user.deactivate", object_type="user", object_id=user.id)
    return user


@router.post("/{user_id}/activate", response_model=UserResponse, summary="Reactivate a user")
async def activate_user(
    user_id: str,
    session: AsyncSession = Depends(get_db),
    admin=Security(require_scope, scopes=["user:manage"]),
) -> UserResponse:
    try:
        user = await user_admin.set_enabled(session, user_id, True)
    except user_admin.UserAdminError as exc:
        raise _map_error(exc) from exc
    await record_audit(session, admin, "user.activate", object_type="user", object_id=user.id)
    return user
