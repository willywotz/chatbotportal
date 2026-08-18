"""Tests for app.routers.users — endpoints called directly with an injected admin."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.errors import ApiError
from app.models.user import User
from app.routers import users as users_router
from app.schemas.user import UserCreate, UserUpdate


async def _admin(email="admin@example.com"):
    return await User.create(email=email, hashed_password="x", role="admin", is_active=True)


async def _user(email="u@example.com", role="user", active=True):
    return await User.create(email=email, hashed_password="x", role=role, is_active=active)


async def _ephemeral(email="anon@example.com"):
    return await User.create(email=email, hashed_password="x", role="user", is_active=True, is_ephemeral=True)


@pytest.mark.asyncio
async def test_list_returns_all(db):
    admin = await _admin()
    await _user(email="a@example.com")
    await _user(email="b@example.com")
    res = await users_router.list_users(search=None, role=None, status_filter="all", admin=admin)
    assert res.total == 3
    assert len(res.data) == 3


@pytest.mark.asyncio
async def test_list_excludes_ephemeral_users(db):
    admin = await _admin()
    await _user(email="real@example.com")
    await _ephemeral(email="anon@example.com")
    res = await users_router.list_users(search=None, role=None, status_filter="all", admin=admin)
    emails = {u.email for u in res.data}
    assert "anon@example.com" not in emails
    assert emails == {"admin@example.com", "real@example.com"}
    assert res.total == 2


@pytest.mark.asyncio
async def test_list_search_filters_by_email(db):
    admin = await _admin()
    await _user(email="needle@example.com")
    res = await users_router.list_users(search="needle", role=None, status_filter="all", admin=admin)
    assert res.total == 1
    assert res.data[0].email == "needle@example.com"


@pytest.mark.asyncio
async def test_list_role_and_status_filters(db):
    admin = await _admin()
    await _user(email="active@example.com", active=True)
    await _user(email="inactive@example.com", active=False)
    active_only = await users_router.list_users(search=None, role="user", status_filter="active", admin=admin)
    assert {u.email for u in active_only.data} == {"active@example.com"}


@pytest.mark.asyncio
async def test_create_with_password_returns_201_shape(db):
    admin = await _admin()
    res = await users_router.create_user(
        UserCreate(email="new@example.com", password="secret123"), admin=admin
    )
    assert res["user"]["email"] == "new@example.com"
    assert "email_sent" not in res  # password mode adds no invite metadata


@pytest.mark.asyncio
async def test_get_single_404(db):
    admin = await _admin()
    with pytest.raises(ApiError) as exc:
        await users_router.get_user(uuid.uuid4(), admin=admin)
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_patch_updates_display_name_and_role(db):
    admin = await _admin()
    target = await _user(email="t@example.com")
    res = await users_router.update_user(
        target.id, UserUpdate(display_name="New Name", role="admin"), admin=admin
    )
    assert res.displayName == "New Name"
    assert res.role == "admin"


@pytest.mark.asyncio
async def test_patch_updates_password(db):
    from app.auth.security import verify_password

    admin = await _admin()
    target = await _user(email="t@example.com")
    await users_router.update_user(
        target.id, UserUpdate(password="newsecret123"), admin=admin
    )
    await target.refresh_from_db()
    assert verify_password("newsecret123", target.hashed_password)


@pytest.mark.asyncio
async def test_patch_rejects_short_password(db):
    admin = await _admin()
    target = await _user(email="t@example.com")
    with pytest.raises(ApiError) as exc:
        await users_router.update_user(
            target.id, UserUpdate(password="123"), admin=admin
        )
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_patch_self_role_change_blocked(db):
    admin = await _admin()
    with pytest.raises(ApiError) as exc:
        await users_router.update_user(admin.id, UserUpdate(role="user"), admin=admin)
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_patch_demote_other_admin_allowed(db):
    # Demoting a *different* admin always leaves the acting admin active, so it
    # is allowed. (The zero-active-admins case is unreachable at the router
    # level once self-action is blocked — it is unit-tested directly against
    # ensure_not_last_admin in test_users_service.py.)
    admin = await _admin()
    target = await _user(email="admin2@example.com", role="admin")
    res = await users_router.update_user(target.id, UserUpdate(role="user"), admin=admin)
    assert res.role == "user"


@pytest.mark.asyncio
async def test_deactivate_sets_inactive(db):
    admin = await _admin()
    target = await _user(email="t@example.com")
    res = await users_router.deactivate_user(target.id, admin=admin)
    assert res.isActive is False


@pytest.mark.asyncio
async def test_deactivate_self_blocked(db):
    admin = await _admin()
    with pytest.raises(ApiError) as exc:
        await users_router.deactivate_user(admin.id, admin=admin)
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_deactivate_other_admin_allowed(db):
    # Deactivating a different admin leaves the acting admin active → allowed.
    admin = await _admin()
    target = await _user(email="admin2@example.com", role="admin")
    res = await users_router.deactivate_user(target.id, admin=admin)
    assert res.isActive is False


@pytest.mark.asyncio
async def test_activate_sets_active(db):
    admin = await _admin()
    target = await _user(email="t@example.com", active=False)
    res = await users_router.activate_user(target.id, admin=admin)
    assert res.isActive is True


@pytest.mark.asyncio
async def test_activate_user_404(db):
    admin = await _admin()
    with pytest.raises(ApiError) as exc:
        await users_router.activate_user(uuid.uuid4(), admin=admin)
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_update_user_404(db):
    admin = await _admin()
    with pytest.raises(ApiError) as exc:
        await users_router.update_user(uuid.uuid4(), UserUpdate(display_name="X"), admin=admin)
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_list_search_filters_by_display_name(db):
    admin = await _admin()
    await User.create(email="match@example.com", hashed_password="x", role="user", is_active=True, display_name="Distinctive Name")
    await _user(email="other@example.com")
    res = await users_router.list_users(search="Distinctive", role=None, status_filter="all", admin=admin)
    assert res.total == 1
    assert res.data[0].email == "match@example.com"
