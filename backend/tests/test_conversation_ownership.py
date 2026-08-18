"""Ownership check on GET/DELETE /conversations/{id} and its /messages sibling.

Pins the scope-based ownership semantics: a conversation with a NULL user_id
(an anonymous chat) is denied to any caller without `conversation:read:all`,
since str(None) never equals str(principal.id).
"""
import uuid

import pytest

from app.auth.keycloak import Principal
from app.errors import ApiError
from app.models.conversation import Conversation
from app.models.user import User
from app.routers.conversations import (
    delete_conversation,
    get_conversation,
    get_conversation_messages,
)


async def _anonymous_conversation() -> Conversation:
    return await Conversation.create(title="t", status="active")


async def _principal(*, read_all: bool = False) -> Principal:
    user = await User.create(email=f"{uuid.uuid4()}@x.com", hashed_password="h", role="user")
    scopes = {"conversation:read:own", "conversation:write:own"}
    if read_all:
        scopes.add("conversation:read:all")
    return Principal(id=str(user.id), email=None, display_name=None, role="admin" if read_all else "user",
                      scopes=frozenset(scopes))


async def test_non_admin_denied_read_of_anonymous_conversation(db):
    other = await _principal()
    conv = await _anonymous_conversation()
    with pytest.raises(ApiError) as exc:
        await get_conversation(conv.id, other)
    assert exc.value.status == 403


async def test_non_admin_denied_read_messages_of_anonymous_conversation(db):
    other = await _principal()
    conv = await _anonymous_conversation()
    with pytest.raises(ApiError) as exc:
        await get_conversation_messages(conv.id, other)
    assert exc.value.status == 403


async def test_non_admin_denied_delete_of_anonymous_conversation(db):
    other = await _principal()
    conv = await _anonymous_conversation()
    with pytest.raises(ApiError) as exc:
        await delete_conversation(conv.id, other)
    assert exc.value.status == 403


async def test_admin_can_read_anonymous_conversation(db):
    admin = await _principal(read_all=True)
    conv = await _anonymous_conversation()
    result = await get_conversation(conv.id, admin)
    assert result["id"] == str(conv.id)


async def test_owner_can_read_own_conversation(db):
    owner = await _principal()
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    result = await get_conversation(conv.id, owner)
    assert result["id"] == str(conv.id)


async def test_other_user_denied_read_of_owned_conversation(db):
    owner = await _principal()
    other = await _principal()
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    with pytest.raises(ApiError) as exc:
        await get_conversation(conv.id, other)
    assert exc.value.status == 403


async def test_other_user_denied_read_messages_of_owned_conversation(db):
    owner = await _principal()
    other = await _principal()
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    with pytest.raises(ApiError) as exc:
        await get_conversation_messages(conv.id, other)
    assert exc.value.status == 403


async def test_other_user_denied_delete_of_owned_conversation(db):
    owner = await _principal()
    other = await _principal()
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    with pytest.raises(ApiError) as exc:
        await delete_conversation(conv.id, other)
    assert exc.value.status == 403
