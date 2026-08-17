"""
Business logic for user-owned API keys.

Kept separate from the router so the ownership guard (404 on cross-user
access) and expiry validation can be unit-tested directly.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import HTTPException, status

from app.auth.security import generate_api_key, hash_api_key
from app.models.user import UserAPIKey
from app.utils import now


async def list_for_user(user_id: uuid.UUID) -> list[UserAPIKey]:
    return await UserAPIKey.filter(user_id=user_id).order_by("-created_at").all()


async def create(user_id: uuid.UUID, name: str, expires_in_days: int | None) -> tuple[UserAPIKey, str]:
    """Create a key and return it with its one-time plaintext value."""
    if expires_in_days is not None and expires_in_days <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="expires_in_days must be positive")
    expires_at = now() + timedelta(days=expires_in_days) if expires_in_days else None
    raw = generate_api_key()
    key = await UserAPIKey.create(
        user_id=user_id, name=name,
        key_hash=hash_api_key(raw), key_prefix=raw[:12],
        expires_at=expires_at,
    )
    return key, raw


async def _get_owned(key_id: str, user_id: uuid.UUID) -> UserAPIKey:
    key = await UserAPIKey.filter(id=key_id, user_id=user_id).first()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return key


async def rename(key_id: str, user_id: uuid.UUID, name: str) -> UserAPIKey:
    key = await _get_owned(key_id, user_id)
    key.name = name
    await key.save()
    return key


async def delete(key_id: str, user_id: uuid.UUID) -> None:
    key = await _get_owned(key_id, user_id)
    await key.delete()


async def revoke(key_id: str, user_id: uuid.UUID) -> UserAPIKey:
    key = await _get_owned(key_id, user_id)
    if key.revoked_at is None:
        key.revoked_at = now()
        await key.save(update_fields=["revoked_at"])
    return key
