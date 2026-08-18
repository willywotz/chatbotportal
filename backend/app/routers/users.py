from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Security, status

from app.auth.dependencies import require_scope
from app.errors import ApiError, ErrorCode
from app.schemas.user import Role, UserCreate, UserCreateResponse, UserListResponse, UserResponse, UserUpdate
from app.services import keycloak_admin
from app.services.audit import record_audit

router = APIRouter(prefix="/users", tags=["Users"])


def _map_error(exc: keycloak_admin.KeycloakAdminError) -> ApiError:
    if isinstance(exc, keycloak_admin.NotFound):
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
    admin=Security(require_scope, scopes=["user:manage"]),
) -> UserListResponse:
    is_active = None if status_filter == "all" else (status_filter == "active")
    try:
        rows, total = await keycloak_admin.list_users(search=search, role=role, is_active=is_active)
    except keycloak_admin.KeycloakAdminError as exc:
        raise _map_error(exc) from exc
    return UserListResponse(data=rows, total=total)


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED, summary="Create a user")
async def create_user(body: UserCreate, admin=Security(require_scope, scopes=["user:manage"])) -> dict:
    try:
        new_user = await keycloak_admin.create_user(body)
    except keycloak_admin.KeycloakAdminError as exc:
        raise _map_error(exc) from exc
    await record_audit(admin, "user.create", object_type="user", object_id=new_user.id, detail={"email": new_user.email, "role": new_user.role})
    return {"user": new_user.model_dump()}


@router.get("/{user_id}", response_model=UserResponse, summary="Get user by ID")
async def get_user(user_id: str, admin=Security(require_scope, scopes=["user:manage"])) -> UserResponse:
    try:
        return await keycloak_admin.get_user(user_id)
    except keycloak_admin.KeycloakAdminError as exc:
        raise _map_error(exc) from exc


@router.patch("/{user_id}", response_model=UserResponse, summary="Update a user")
async def update_user(user_id: str, body: UserUpdate, admin=Security(require_scope, scopes=["user:manage"])) -> UserResponse:
    try:
        user = await keycloak_admin.update_user(user_id, body)
    except keycloak_admin.KeycloakAdminError as exc:
        raise _map_error(exc) from exc
    changed = [f for f in ("role", "display_name", "password") if getattr(body, f) is not None]
    if changed:
        await record_audit(
            admin, "user.update", object_type="user", object_id=user.id,
            detail={"changed": changed, "role": user.role},
        )
    return user


@router.post("/{user_id}/deactivate", response_model=UserResponse, summary="Deactivate a user")
async def deactivate_user(user_id: str, admin=Security(require_scope, scopes=["user:manage"])) -> UserResponse:
    try:
        user = await keycloak_admin.set_enabled(user_id, False)
    except keycloak_admin.KeycloakAdminError as exc:
        raise _map_error(exc) from exc
    await record_audit(admin, "user.deactivate", object_type="user", object_id=user.id)
    return user


@router.post("/{user_id}/activate", response_model=UserResponse, summary="Reactivate a user")
async def activate_user(user_id: str, admin=Security(require_scope, scopes=["user:manage"])) -> UserResponse:
    try:
        user = await keycloak_admin.set_enabled(user_id, True)
    except keycloak_admin.KeycloakAdminError as exc:
        raise _map_error(exc) from exc
    await record_audit(admin, "user.activate", object_type="user", object_id=user.id)
    return user
