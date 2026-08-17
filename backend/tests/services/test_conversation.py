"""Service-layer tests for conversation data access (moved out of the router)."""

import uuid

import pytest
from fastapi import HTTPException

from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.conversation import MessageIn, SaveConversationRequest
from app.services import conversation as conversation_service


async def test_create_conversation_persists_conversation_and_messages(db):
    body = SaveConversationRequest(
        title="visa help",
        preview="p",
        status="success",
        messages=[MessageIn(role="user", content="hi")],
    )
    conv = await conversation_service.create_conversation(body, None)
    assert conv.title == "visa help"
    assert await Message.filter(conversation_id=conv.id).count() == 1


async def test_list_conversations_filters_by_search_and_reports_total(db):
    owner = await User.create(email="owner@x.com", hashed_password="h", role="user", is_admin=False)
    await Conversation.create(title="visa renewal", preview="p", status="success", message_count=1, user_id=owner.id)
    await Conversation.create(title="tax return", preview="p", status="success", message_count=1, user_id=owner.id)

    rows, total = await conversation_service.list_conversations(
        user=owner, search="visa", filter_agency="", date_from=None, date_to=None,
        page=1, page_size=None,
    )
    assert total == 1
    assert [r.title for r in rows] == ["visa renewal"]


async def test_list_conversations_rejects_bad_date_from(db):
    owner = await User.create(email="owner2@x.com", hashed_password="h", role="user", is_admin=False)
    with pytest.raises(HTTPException) as exc:
        await conversation_service.list_conversations(
            user=owner, search="", filter_agency="", date_from="not-a-date", date_to=None,
            page=1, page_size=None,
        )
    assert exc.value.status_code == 400


async def test_get_conversation_with_messages_denies_non_owner(db):
    owner = await User.create(email="owner3@x.com", hashed_password="h", role="user", is_admin=False)
    other = await User.create(email="other3@x.com", hashed_password="h", role="user", is_admin=False)
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    with pytest.raises(HTTPException) as exc:
        await conversation_service.get_conversation_with_messages(conv.id, other)
    assert exc.value.status_code == 403


async def test_delete_conversation_removes_row(db):
    owner = await User.create(email="owner4@x.com", hashed_password="h", role="user", is_admin=False)
    conv = await Conversation.create(title="t", status="active", user_id=owner.id)
    await conversation_service.delete_conversation(conv.id, owner)
    assert await Conversation.get_or_none(id=conv.id) is None
