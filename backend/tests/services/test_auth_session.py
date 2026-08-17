from datetime import timedelta

import pytest

from app.models.user import User
from app.services.auth_session import (
    create_session, delete_session, expire_session, remaining_ttl, resolve_session,
)
from app.utils import now


@pytest.fixture
async def make_user(db):
    async def _make():
        return await User.create(
            email="u@example.com", hashed_password="x", role="user"
        )
    return _make


@pytest.mark.asyncio
async def test_create_and_resolve_roundtrip(db, make_user):
    user = await make_user()
    sid = await create_session(str(user.id))
    assert sid
    assert await resolve_session(sid) == str(user.id)


@pytest.mark.asyncio
async def test_expired_session_returns_none_and_is_deleted(db, make_user):
    from app.models.session import Session

    user = await make_user()
    sid = await create_session(str(user.id))
    # Force expiry in the past.
    await Session.filter(id=sid).update(expires_at=now() - timedelta(seconds=1))
    assert await resolve_session(sid) is None
    assert await Session.filter(id=sid).count() == 0


@pytest.mark.asyncio
async def test_delete_session_removes_row(db, make_user):
    user = await make_user()
    sid = await create_session(str(user.id))
    await delete_session(sid)
    assert await resolve_session(sid) is None


@pytest.mark.asyncio
async def test_expire_session_shortens_ttl_and_still_resolves(db, make_user):
    user = await make_user()
    sid = await create_session(str(user.id))
    await expire_session(sid, 5)
    ttl = await remaining_ttl(sid)
    assert ttl is not None and ttl <= 5
    assert await resolve_session(sid) == str(user.id)


@pytest.mark.asyncio
async def test_remaining_ttl_none_for_missing(db):
    assert await remaining_ttl("does-not-exist") is None


@pytest.mark.asyncio
async def test_delete_and_expire_on_missing_sid_are_noops(db):
    await delete_session("missing")          # no raise
    await expire_session("missing", 5)       # no raise
