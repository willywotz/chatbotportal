import pytest
from fastapi import HTTPException

from app.models.conversation import Conversation, Message
from app.models.user import User
from app.routers.conversations import get_conversation_messages
from app.services.responses.continuity import resolve_conversation
from app.services.responses.errors import ResponsesApiError
from app.utils import now


@pytest.mark.asyncio
async def test_continuity_ignores_soft_deleted_assistant_message(db):
    c = await Conversation.create(title="t")
    m = await Message.create(
        conversation_id=c.id, role="assistant", content="a", deleted_at=now()
    )
    with pytest.raises(ResponsesApiError):
        await resolve_conversation(
            previous_response_id=f"resp_{m.id}", conversation=None, cache=None
        )


@pytest.mark.asyncio
async def test_continuity_resolves_live_assistant_message(db):
    c = await Conversation.create(title="t")
    m = await Message.create(conversation_id=c.id, role="assistant", content="a")
    conv_id, is_cont = await resolve_conversation(
        previous_response_id=f"resp_{m.id}", conversation=None, cache=None
    )
    assert conv_id == str(c.id) and is_cont is True


@pytest.mark.asyncio
async def test_get_messages_404s_for_soft_deleted_conversation(db):
    owner = await User.create(email="owner-soft-del@x.com", hashed_password="h", role="user")
    conv = await Conversation.create(
        title="t", status="active", user_id=owner.id, deleted_at=now()
    )
    with pytest.raises(HTTPException) as exc:
        await get_conversation_messages(conv.id, owner)
    assert exc.value.status_code == 404
