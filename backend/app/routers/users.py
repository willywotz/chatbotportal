from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import require_admin
from app.models.user import User
from app.schemas.user import Role, UserCreate, UserCreateResponse, UserListResponse, UserResponse, UserUpdate
from app.services import user as user_service
from app.services.audit import record_audit

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=UserListResponse, summary="List users")
async def list_users(
    search: str | None = Query(None, description="Search email or display name"),
    role: Role | None = Query(None, description="Filter by role: user | admin"),
    status_filter: Literal["active", "inactive", "all"] = Query(
        "all", alias="status", description="Filter by active status"
    ),
    admin: User = Depends(require_admin),
) -> UserListResponse:
    rows = await user_service.list_users(search=search, role=role, status_filter=status_filter)
    return UserListResponse(
        data=[UserResponse.from_user(u) for u in rows],
        total=len(rows),
    )


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED, summary="Create a user")
async def create_user(body: UserCreate, admin: User = Depends(require_admin)) -> dict:
    new_user = await user_service.create_user(body)
    await record_audit(admin, "user.create", object_type="user", object_id=new_user.id, detail={"email": new_user.email, "role": new_user.role})
    return {"user": UserResponse.from_user(new_user).model_dump()}


@router.get("/{user_id}", response_model=UserResponse, summary="Get user by ID")
async def get_user(user_id: uuid.UUID, admin: User = Depends(require_admin)) -> UserResponse:
    user = await user_service.get_user_or_404(user_id)
    return UserResponse.from_user(user)


@router.patch("/{user_id}", response_model=UserResponse, summary="Update a user")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, admin: User = Depends(require_admin)
) -> UserResponse:
    user = await user_service.get_user_or_404(user_id)
    changed = await user_service.apply_update(admin.id, user, body)
    if changed:
        audit_changed = ["password" if c == "hashed_password" else c for c in changed]
        await record_audit(
            admin, "user.update", object_type="user", object_id=user.id,
            detail={"changed": audit_changed, "role": user.role},
        )
    return UserResponse.from_user(user)


@router.post("/{user_id}/deactivate", response_model=UserResponse, summary="Deactivate (soft-delete) a user")
async def deactivate_user(user_id: uuid.UUID, admin: User = Depends(require_admin)) -> UserResponse:
    user = await user_service.get_user_or_404(user_id)
    await user_service.deactivate(admin.id, user)
    await record_audit(admin, "user.deactivate", object_type="user", object_id=user.id)
    return UserResponse.from_user(user)


@router.post("/{user_id}/activate", response_model=UserResponse, summary="Reactivate a user")
async def activate_user(user_id: uuid.UUID, admin: User = Depends(require_admin)) -> UserResponse:
    user = await user_service.get_user_or_404(user_id)
    await user_service.activate(user)
    await record_audit(admin, "user.activate", object_type="user", object_id=user.id)
    return UserResponse.from_user(user)
