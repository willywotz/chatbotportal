"""Local user administration — backs the admin Users page.

Replaces the Keycloak Admin REST proxy: accounts now live in the `users`
table. Kept free of FastAPI imports (this is a service, not a router). Callers
own the transaction; this module never commits."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc.passwords import hash_password
from app.models.user import User, UserRole
from app.repositories import user as user_repo
from app.schemas.user import Role, UserResponse


class UserAdminError(Exception):
    def __init__(self, message: str, *, status: int):
        super().__init__(message)
        self.status = status


class NotFound(UserAdminError):
    def __init__(self, message: str = "User not found"):
        super().__init__(message, status=404)


class Conflict(UserAdminError):
    def __init__(self, message: str = "Email already in use"):
        super().__init__(message, status=409)


def _map_user(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        displayName=user.display_name or user.email,
        role=user.role.value,
        avatarUrl=None,
        isActive=user.is_active,
        createdAt=user.created_at,
    )


async def _require(session: AsyncSession, user_id: str) -> User:
    try:
        parsed = uuid.UUID(str(user_id))
    except ValueError as exc:
        raise NotFound() from exc
    user = await user_repo.get(session, parsed)
    if user is None:
        raise NotFound()
    return user


async def list_users(
    session: AsyncSession,
    *,
    search: str | None = None,
    role: Role | None = None,
    is_active: bool | None = None,
) -> tuple[list[UserResponse], int]:
    role_enum = UserRole(role) if role is not None else None
    rows = await user_repo.list_users(session, search=search, role=role_enum, is_active=is_active)
    users = [_map_user(u) for u in rows]
    return users, len(users)


async def get_user(session: AsyncSession, user_id: str) -> UserResponse:
    return _map_user(await _require(session, user_id))


async def create_user(session: AsyncSession, data) -> UserResponse:
    if await user_repo.get_by_email(session, data.email) is not None:
        raise Conflict()
    user = await user_repo.create(
        session,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole(data.role),
        display_name=data.display_name,
    )
    return _map_user(user)


async def update_user(session: AsyncSession, user_id: str, data) -> UserResponse:
    user = await _require(session, user_id)
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.role is not None:
        user.role = UserRole(data.role)
    if data.password is not None:
        user.password_hash = hash_password(data.password)
    await session.flush()
    return _map_user(user)


async def set_enabled(session: AsyncSession, user_id: str, enabled: bool) -> UserResponse:
    user = await _require(session, user_id)
    user.is_active = enabled
    await session.flush()
    return _map_user(user)


async def delete_user(session: AsyncSession, user_id: str) -> None:
    user = await _require(session, user_id)
    await user_repo.delete(session, user)
