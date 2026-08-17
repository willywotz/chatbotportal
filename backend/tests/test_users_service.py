"""Tests for app.services.user — create flow and guardrails."""

import uuid

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services import user as user_service


async def _make_admin(email="admin@example.com", active=True):
    return await User.create(
        email=email, hashed_password="x", role="admin", is_active=active
    )


@pytest.mark.asyncio
async def test_create_with_password_hashes_and_persists(db):
    created = await user_service.create_user(
        UserCreate(email="new@example.com", role="user", password="secret123")
    )
    assert created.id is not None
    assert created.hashed_password != "secret123"


@pytest.mark.asyncio
async def test_create_rejects_short_password(db):
    with pytest.raises(HTTPException) as exc:
        await user_service.create_user(
            UserCreate(email="x@example.com", password="123")
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_rejects_duplicate_email(db):
    await _make_admin(email="dup@example.com")
    with pytest.raises(HTTPException) as exc:
        await user_service.create_user(
            UserCreate(email="dup@example.com", password="secret123")
        )
    assert exc.value.status_code == 409


def test_ensure_not_self_blocks_same_id():
    uid = uuid.uuid4()
    with pytest.raises(HTTPException) as exc:
        user_service.ensure_not_self(uid, uid)
    assert exc.value.status_code == 400


def test_ensure_not_self_allows_different_id():
    user_service.ensure_not_self(uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_ensure_not_last_admin_blocks_demoting_only_admin(db):
    admin = await _make_admin()
    with pytest.raises(HTTPException) as exc:
        await user_service.ensure_not_last_admin(admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_ensure_not_last_admin_allows_when_another_admin_exists(db):
    admin = await _make_admin()
    await _make_admin(email="admin2@example.com")
    await user_service.ensure_not_last_admin(admin)


@pytest.mark.asyncio
async def test_ensure_not_last_admin_ignores_non_admin_target(db):
    await _make_admin()
    plain = await User.create(email="u@example.com", hashed_password="x", role="user")
    await user_service.ensure_not_last_admin(plain)


@pytest.mark.asyncio
async def test_list_users_excludes_ephemeral_and_filters(db):
    await _make_admin(email="a@example.com")
    await User.create(email="plain@example.com", hashed_password="x", role="user")
    await User.create(email="ghost@example.com", hashed_password="x", role="user",
                      is_ephemeral=True)

    rows = await user_service.list_users(search=None, role=None, status_filter="all")
    emails = {u.email for u in rows}
    assert "ghost@example.com" not in emails
    assert {"a@example.com", "plain@example.com"} <= emails

    admins = await user_service.list_users(search=None, role="admin", status_filter="all")
    assert [u.email for u in admins] == ["a@example.com"]

    found = await user_service.list_users(search="plain", role=None, status_filter="all")
    assert [u.email for u in found] == ["plain@example.com"]


@pytest.mark.asyncio
async def test_get_user_or_404_raises_for_missing(db):
    with pytest.raises(HTTPException) as exc:
        await user_service.get_user_or_404(uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_apply_update_changes_display_name(db):
    user = await User.create(email="u2@example.com", hashed_password="x", role="user")
    changed = await user_service.apply_update(uuid.uuid4(), user, UserUpdate(display_name="New"))
    assert changed == ["display_name"]
    refreshed = await User.get(id=user.id)
    assert refreshed.display_name == "New"


@pytest.mark.asyncio
async def test_deactivate_and_activate_toggle_is_active(db):
    admin = await _make_admin(email="keep-admin@example.com")
    user = await User.create(email="u3@example.com", hashed_password="x", role="user")
    await user_service.deactivate(admin.id, user)
    assert (await User.get(id=user.id)).is_active is False
    await user_service.activate(user)
    assert (await User.get(id=user.id)).is_active is True

@pytest.mark.asyncio
async def test_get_active_by_email_finds_active_user(db):
    await User.create(email="active@example.com", hashed_password="x", is_active=True)
    found = await user_service.get_active_by_email("active@example.com")
    assert found is not None and found.email == "active@example.com"


@pytest.mark.asyncio
async def test_get_active_by_email_ignores_inactive_user(db):
    await User.create(email="inactive@example.com", hashed_password="x", is_active=False)
    assert await user_service.get_active_by_email("inactive@example.com") is None


@pytest.mark.asyncio
async def test_get_active_by_id_finds_active_user(db):
    user = await User.create(email="byid@example.com", hashed_password="x", is_active=True)
    found = await user_service.get_active_by_id(user.id)
    assert found is not None and found.id == user.id


@pytest.mark.asyncio
async def test_get_active_by_id_ignores_inactive_user(db):
    user = await User.create(email="byid2@example.com", hashed_password="x", is_active=False)
    assert await user_service.get_active_by_id(user.id) is None


@pytest.mark.asyncio
async def test_create_anonymous_makes_ephemeral_user(db):
    anon = await user_service.create_anonymous()
    assert anon.is_ephemeral is True
    assert anon.role == "user"
    assert anon.email.startswith("anon-") and anon.email.endswith("@ephemeral.local")
