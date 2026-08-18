"""Tests for POST /auth/change-password — self-service password change."""

import pytest
from fastapi import HTTPException

from app.auth.security import hash_password, verify_password
from app.models.user import User
from app.routers import auth as auth_router
from app.routers.auth import ChangePasswordRequest


async def _user(pw="oldsecret"):
    return await User.create(
        email="u@example.com", hashed_password=hash_password(pw), role="user", is_active=True
    )


@pytest.mark.asyncio
async def test_change_password_success(db):
    user = await _user()
    res = await auth_router.change_password(
        ChangePasswordRequest(current_password="oldsecret", new_password="newsecret123"),
        user=user,
    )
    assert "message" in res
    await user.refresh_from_db()
    assert verify_password("newsecret123", user.hashed_password)


@pytest.mark.asyncio
async def test_change_password_wrong_current(db):
    user = await _user()
    with pytest.raises(HTTPException) as exc:
        await auth_router.change_password(
            ChangePasswordRequest(current_password="wrong", new_password="newsecret123"),
            user=user,
        )
    assert exc.value.status_code == 400
    await user.refresh_from_db()
    assert verify_password("oldsecret", user.hashed_password)


@pytest.mark.asyncio
async def test_change_password_rejects_short_new(db):
    from app.errors import ApiError

    user = await _user()
    with pytest.raises(ApiError) as exc:
        await auth_router.change_password(
            ChangePasswordRequest(current_password="oldsecret", new_password="123"),
            user=user,
        )
    assert exc.value.status == 400
