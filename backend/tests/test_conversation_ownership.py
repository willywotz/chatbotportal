"""Ownership check on GET/DELETE /conversations/{id} and its /messages sibling.

Pins the semantics carried over from the deleted authorize(): a conversation
with a NULL user_id (an anonymous chat) is denied to any non-admin caller,
since str(None) never equals str(user.id).
"""
import pytest
from fastapi import HTTPException

from app.models.conversation import Conversation
from app.models.user import User
from app.routers.conversations import (
    delete_conversation,
    get_conversation,
    get_conversation_messages,
)


async def _anonymous_conversation() -> Conversation:
    return await Conversation.create(title="t", status="active")


async def test_non_admin_denied_read_of_anonymous_conversation(db):
    other = await User.create(email="other-read@x.com", hashed_password="h", role="user")
    conv = await _anonymous_conversation()
    with pytest.raises(HTTPException) as exc:
        await get_conversation(conv.id, other)
    assert exc.value.status_code == 403


async def test_non_admin_denied_read_messages_of_anonymous_conversation(db):
    other = await User.create(email="other-msgs@x.com", hashed_password="h", role="user")
    conv = await _anonymous_conversation()
    with pytest.raises(HTTPException) as exc:
        await get_conversation_messages(conv.id, other)
    assert exc.value.status_code == 403


async def test_non_admin_denied_delete_of_anonymous_conversation(db):
    other = await User.create(email="other-delete@x.com", hashed_password="h", role="user")
    conv = await _anonymous_conversation()
    with pytest.raises(HTTPException) as exc:
        await delete_conversation(conv.id, other)
    assert exc.value.status_code == 403


async def test_admin_can_read_anonymous_conversation(db):
    admin = await User.create(email="admin-read@x.com", hashed_password="h", role="admin")
    conv = await _anonymous_conversation()
    result = await get_conversation(conv.id, admin)
    assert result["id"] == str(conv.id)


async def test_owner_can_read_own_conversation(db):
    owner = await User.create(email="owner-read@x.com", hashed_password="h", role="user")
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    result = await get_conversation(conv.id, owner)
    assert result["id"] == str(conv.id)


async def test_other_user_denied_read_of_owned_conversation(db):
    owner = await User.create(email="owner-a@x.com", hashed_password="h", role="user")
    other = await User.create(email="other-b@x.com", hashed_password="h", role="user")
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    with pytest.raises(HTTPException) as exc:
        await get_conversation(conv.id, other)
    assert exc.value.status_code == 403


async def test_other_user_denied_read_messages_of_owned_conversation(db):
    owner = await User.create(email="owner-c@x.com", hashed_password="h", role="user")
    other = await User.create(email="other-d@x.com", hashed_password="h", role="user")
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    with pytest.raises(HTTPException) as exc:
        await get_conversation_messages(conv.id, other)
    assert exc.value.status_code == 403


async def test_other_user_denied_delete_of_owned_conversation(db):
    owner = await User.create(email="owner-e@x.com", hashed_password="h", role="user")
    other = await User.create(email="other-f@x.com", hashed_password="h", role="user")
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    with pytest.raises(HTTPException) as exc:
        await delete_conversation(conv.id, other)
    assert exc.value.status_code == 403
