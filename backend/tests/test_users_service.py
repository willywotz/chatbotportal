"""Tests for app.services.user — the session-auth helpers still used by
app.routers.auth (login-by-email, anonymous sessions). Admin user-management
now lives in app.services.keycloak_admin (tests/test_users_proxy.py)."""

from app.models.user import User
from app.services import user as user_service


async def test_get_active_by_email_finds_active_user(db):
    await User.create(email="active@example.com", hashed_password="x", is_active=True)
    found = await user_service.get_active_by_email("active@example.com")
    assert found is not None and found.email == "active@example.com"


async def test_get_active_by_email_ignores_inactive_user(db):
    await User.create(email="inactive@example.com", hashed_password="x", is_active=False)
    assert await user_service.get_active_by_email("inactive@example.com") is None


async def test_get_active_by_id_finds_active_user(db):
    user = await User.create(email="byid@example.com", hashed_password="x", is_active=True)
    found = await user_service.get_active_by_id(user.id)
    assert found is not None and found.id == user.id


async def test_get_active_by_id_ignores_inactive_user(db):
    user = await User.create(email="byid2@example.com", hashed_password="x", is_active=False)
    assert await user_service.get_active_by_id(user.id) is None


async def test_create_anonymous_makes_ephemeral_user(db):
    anon = await user_service.create_anonymous()
    assert anon.is_ephemeral is True
    assert anon.role == "user"
    assert anon.email.startswith("anon-") and anon.email.endswith("@ephemeral.local")
