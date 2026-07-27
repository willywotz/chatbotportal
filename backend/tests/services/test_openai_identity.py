"""Ownership check for OpenAI-surface rows."""
import pytest

from app.models.user import User
from app.services.openai.identity import owns

pytestmark = pytest.mark.asyncio


async def test_owner_owns_their_row(db):
    u = await User.create(email="real@x.y", hashed_password="!")
    assert owns(type("R", (), {"user_id": u.id})(), u) is True


async def test_non_owner_does_not_own(db):
    u = await User.create(email="a@x.y", hashed_password="!")
    other = await User.create(email="b@x.y", hashed_password="!")
    assert owns(type("R", (), {"user_id": u.id})(), other) is False


async def test_anonymous_never_owns(db):
    u = await User.create(email="c@x.y", hashed_password="!")
    assert owns(type("R", (), {"user_id": u.id})(), None) is False


async def test_admin_owns_any_row(db):
    u = await User.create(email="d@x.y", hashed_password="!")
    admin = await User.create(email="admin@x.y", hashed_password="!", role="admin")
    assert owns(type("R", (), {"user_id": u.id})(), admin) is True
