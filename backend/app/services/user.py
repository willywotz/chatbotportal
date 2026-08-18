"""
Business logic for admin user management.

Kept separate from the router so guardrails (no self-mutation, protect the last
active admin) and password validation can be unit-tested directly.
"""

from __future__ import annotations

import uuid
from typing import Literal

from app.auth.security import hash_password
from app.config import settings
from app.errors import ApiError, ErrorCode
from app.models.user import User
from app.repositories import user as user_repo
from app.schemas.user import Role, UserCreate, UserUpdate

_ANONYMOUS_PASSWORD_PLACEHOLDER = "!"  # anon users never authenticate with a password


def hash_new_password(password: str) -> str:
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        raise ApiError(ErrorCode.INVALID_REQUEST, "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร", status=400)
    return hash_password(password)


def ensure_not_self(acting_user_id: uuid.UUID, target_id: uuid.UUID) -> None:
    """An admin may not change their own role, deactivate, or delete themselves."""
    if acting_user_id == target_id:
        raise ApiError(ErrorCode.INVALID_REQUEST, "ไม่สามารถดำเนินการกับบัญชีของตนเองได้", status=400)


async def ensure_not_last_admin(target: User) -> None:
    """Reject an action that would leave the system with zero active admins."""
    if target.role != "admin" or not target.is_active:
        return
    others = await user_repo.count_other_active_admins(target.id)
    if others == 0:
        raise ApiError(ErrorCode.INVALID_REQUEST, "ต้องมีผู้ดูแลระบบที่ใช้งานได้อย่างน้อยหนึ่งคน", status=400)


async def create_user(data: UserCreate) -> User:
    hashed = hash_new_password(data.password)

    if await user_repo.email_exists(data.email):
        raise ApiError(ErrorCode.CONFLICT, "อีเมลนี้ถูกใช้งานแล้ว", status=409)

    return await user_repo.create(
        email=data.email,
        display_name=data.display_name,
        hashed_password=hashed,
        role=data.role,
    )


async def list_users(
    *,
    search: str | None,
    role: Role | None,
    status_filter: Literal["active", "inactive", "all"],
) -> list[User]:
    """Return non-ephemeral users, newest first, with optional filters."""
    is_active = None if status_filter == "all" else (status_filter == "active")
    return await user_repo.search(search_text=search, role=role, is_active=is_active)


async def get_user_or_404(user_id: uuid.UUID) -> User:
    user = await user_repo.by_id(user_id)
    if user is None:
        raise ApiError(ErrorCode.NOT_FOUND, "User not found", status=404)
    return user


async def apply_update(admin_id: uuid.UUID, user: User, body: UserUpdate) -> list[str]:
    """Apply a partial update to `user`, persist it, and return the changed fields."""
    changed: list[str] = []
    if body.role is not None and body.role != user.role:
        ensure_not_self(admin_id, user.id)
        if user.role == "admin" and body.role != "admin":
            await ensure_not_last_admin(user)
        user.role = body.role
        changed.append("role")
    if body.display_name is not None:
        user.display_name = body.display_name
        changed.append("display_name")
    if body.password is not None:
        user.hashed_password = hash_new_password(body.password)
        changed.append("hashed_password")
    if changed:
        await user_repo.save(user, update_fields=changed)
    return changed


async def deactivate(admin_id: uuid.UUID, user: User) -> None:
    """Soft-delete a user, keeping at least one active admin."""
    ensure_not_self(admin_id, user.id)
    # Guard is best-effort: a concurrent deactivate could still race (non-transactional).
    await ensure_not_last_admin(user)
    user.is_active = False
    await user_repo.save(user, update_fields=["is_active"])


async def activate(user: User) -> None:
    user.is_active = True
    await user_repo.save(user, update_fields=["is_active"])


async def get_active_by_email(email: str) -> User | None:
    return await user_repo.active_by_email(email)


async def get_active_by_id(user_id: uuid.UUID | str) -> User | None:
    return await user_repo.active_by_id(user_id)


async def create_anonymous() -> User:
    """Create an ephemeral, password-less user for an anonymous session."""
    return await user_repo.create(
        email=f"anon-{uuid.uuid4().hex}@ephemeral.local",
        is_ephemeral=True, role="user", hashed_password=_ANONYMOUS_PASSWORD_PLACEHOLDER,
    )
