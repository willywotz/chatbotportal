"""Ephemeral temp-user identity for anonymous OpenAI-surface callers."""
import pytest

from app.models.user import User
from app.services.openai.identity import owner_or_ephemeral, owns

pytestmark = pytest.mark.asyncio


async def test_anonymous_mints_ephemeral_user_and_token(db):
    user, token = await owner_or_ephemeral(None)
    assert user.is_ephemeral is True
    assert token and token.count(".") == 2  # JWT has two dots
    assert owns(type("R", (), {"user_id": user.id})(), user) is True


async def test_authenticated_caller_is_returned_unchanged(db):
    u = await User.create(email="real@x.y", hashed_password="!")
    user, token = await owner_or_ephemeral(u)
    assert user.id == u.id and token is None
