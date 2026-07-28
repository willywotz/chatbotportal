from datetime import timedelta

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.auth.security import generate_api_key, hash_api_key
from app.models.user import User, UserAPIKey
from app.utils import now


def _request(token: str) -> Request:
    return Request(
        {"type": "http", "method": "GET", "path": "/x",
         "headers": [(b"authorization", f"Bearer {token}".encode())], "query_string": b""}
    )


async def _key(user, **extra):
    raw = generate_api_key()
    await UserAPIKey.create(user_id=user.id, name="n", key_hash=hash_api_key(raw),
                            key_prefix=raw[:12], **extra)
    return raw


async def test_revoked_key_rejected(db):
    u = await User.create(email="r@x.com", hashed_password="h")
    raw = await _key(u, revoked_at=now())
    with pytest.raises(HTTPException) as e:
        await get_current_user(_request(raw))
    assert e.value.status_code == 401


async def test_expired_key_rejected(db):
    u = await User.create(email="e@x.com", hashed_password="h")
    raw = await _key(u, expires_at=now() - timedelta(seconds=1))
    with pytest.raises(HTTPException) as e:
        await get_current_user(_request(raw))
    assert e.value.status_code == 401


async def test_future_expiry_key_works(db):
    u = await User.create(email="f@x.com", hashed_password="h")
    raw = await _key(u, expires_at=now() + timedelta(days=1))
    result = await get_current_user(_request(raw))
    assert result.id == u.id


async def test_optional_revoked_key_raises_401(db):
    u = await User.create(email="or@x.com", hashed_password="h")
    raw = await _key(u, revoked_at=now())
    with pytest.raises(HTTPException) as e:
        await get_current_user_optional(_request(raw))
    assert e.value.status_code == 401


async def test_optional_expired_key_raises_401(db):
    u = await User.create(email="oe@x.com", hashed_password="h")
    raw = await _key(u, expires_at=now() - timedelta(seconds=1))
    with pytest.raises(HTTPException) as e:
        await get_current_user_optional(_request(raw))
    assert e.value.status_code == 401
