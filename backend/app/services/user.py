"""
Business logic for admin user management.

Kept separate from the router so guardrails (no self-mutation, protect the last
active admin) and password validation can be unit-tested directly.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException, status
from tortoise.exceptions import DoesNotExist
from tortoise.expressions import Q

from app.auth.security import hash_password
from app.config import settings
from app.models.user import User
from app.schemas.user import Role, UserCreate, UserUpdate


def hash_new_password(password: str) -> str:
    """Validate a plaintext password and return its bcrypt hash."""
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร",
        )
    return hash_password(password)


def ensure_not_self(acting_user_id: uuid.UUID, target_id: uuid.UUID) -> None:
    """An admin may not change their own role, deactivate, or delete themselves."""
    if acting_user_id == target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ไม่สามารถดำเนินการกับบัญชีของตนเองได้",
        )


async def ensure_not_last_admin(target: User) -> None:
    """Reject an action that would leave the system with zero active admins."""
    if target.role != "admin" or not target.is_active:
        return
    others = await User.filter(role="admin", is_active=True).exclude(id=target.id).count()
    if others == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ต้องมีผู้ดูแลระบบที่ใช้งานได้อย่างน้อยหนึ่งคน",
        )


async def create_user(data: UserCreate) -> User:
    """
    Create a user with an admin-set initial password; the user can log in
    immediately.
    """
    hashed = hash_new_password(data.password)

    if await User.filter(email=data.email).exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="อีเมลนี้ถูกใช้งานแล้ว")

    return await User.create(
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
    qs = User.filter(is_ephemeral=False)
    if search:
        qs = qs.filter(Q(email__icontains=search) | Q(display_name__icontains=search))
    if role:
        qs = qs.filter(role=role)
    if status_filter == "active":
        qs = qs.filter(is_active=True)
    elif status_filter == "inactive":
        qs = qs.filter(is_active=False)
    return await qs.order_by("-created_at")


async def get_user_or_404(user_id: uuid.UUID) -> User:
    """Return one user or raise 404."""
    try:
        return await User.get(id=user_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


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
        await user.save(update_fields=changed)
    return changed


async def deactivate(admin_id: uuid.UUID, user: User) -> None:
    """Soft-delete a user, keeping at least one active admin."""
    ensure_not_self(admin_id, user.id)
    # Guard is best-effort: a concurrent deactivate could still race (non-transactional).
    await ensure_not_last_admin(user)
    user.is_active = False
    await user.save(update_fields=["is_active"])


async def activate(user: User) -> None:
    """Reactivate a soft-deleted user."""
    user.is_active = True
    await user.save(update_fields=["is_active"])
