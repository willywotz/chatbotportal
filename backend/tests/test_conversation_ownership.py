"""Ownership check on GET/DELETE /conversations/{id} and its /messages sibling.

Pins the scope-based ownership semantics: a conversation with a NULL user_id
(an anonymous chat) is denied to any caller without `conversation:read:all`,
since str(None) never equals str(principal.id).
"""
import uuid

import pytest

from app.auth.keycloak import Principal
from app.errors import ApiError
from app.repositories import conversation as conversation_repo
from app.routers.conversations import (
    delete_conversation,
    get_conversation,
    get_conversation_messages,
)


def _principal(*, read_all: bool = False) -> Principal:
    scopes = {"conversation:read:own", "conversation:write:own"}
    if read_all:
        scopes.add("conversation:read:all")
    return Principal(id=str(uuid.uuid4()), email=None, display_name=None,
                      role="admin" if read_all else "user", scopes=frozenset(scopes))


async def test_non_admin_denied_read_of_anonymous_conversation(db_session):
    other = _principal()
    conv = await conversation_repo.create(db_session, title="t", status="active")
    with pytest.raises(ApiError) as exc:
        await get_conversation(conv.id, db_session, other)
    assert exc.value.status == 403


async def test_non_admin_denied_read_messages_of_anonymous_conversation(db_session):
    other = _principal()
    conv = await conversation_repo.create(db_session, title="t", status="active")
    with pytest.raises(ApiError) as exc:
        await get_conversation_messages(conv.id, db_session, other)
    assert exc.value.status == 403


async def test_non_admin_denied_delete_of_anonymous_conversation(db_session):
    other = _principal()
    conv = await conversation_repo.create(db_session, title="t", status="active")
    with pytest.raises(ApiError) as exc:
        await delete_conversation(conv.id, db_session, other)
    assert exc.value.status == 403


async def test_admin_can_read_anonymous_conversation(db_session):
    admin = _principal(read_all=True)
    conv = await conversation_repo.create(db_session, title="t", status="active")
    result = await get_conversation(conv.id, db_session, admin)
    assert result["id"] == str(conv.id)


async def test_owner_can_read_own_conversation(db_session):
    owner = _principal()
    conv = await conversation_repo.create(db_session, title="t", status="active", user_id=owner.id)
    result = await get_conversation(conv.id, db_session, owner)
    assert result["id"] == str(conv.id)


async def test_other_user_denied_read_of_owned_conversation(db_session):
    owner = _principal()
    other = _principal()
    conv = await conversation_repo.create(db_session, title="t", status="active", user_id=owner.id)
    with pytest.raises(ApiError) as exc:
        await get_conversation(conv.id, db_session, other)
    assert exc.value.status == 403


async def test_other_user_denied_read_messages_of_owned_conversation(db_session):
    owner = _principal()
    other = _principal()
    conv = await conversation_repo.create(db_session, title="t", status="active", user_id=owner.id)
    with pytest.raises(ApiError) as exc:
        await get_conversation_messages(conv.id, db_session, other)
    assert exc.value.status == 403


async def test_other_user_denied_delete_of_owned_conversation(db_session):
    owner = _principal()
    other = _principal()
    conv = await conversation_repo.create(db_session, title="t", status="active", user_id=owner.id)
    with pytest.raises(ApiError) as exc:
        await delete_conversation(conv.id, db_session, other)
    assert exc.value.status == 403
