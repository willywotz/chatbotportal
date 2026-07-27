"""Cache-hit must copy the answer into a fresh per-conversation message.

On a cache hit the endpoint previously returned the ORIGINAL message id and
conversation, so rating the answer overwrote the original message's feedback.
These tests pin the fix: a hit creates new records and leaves the original
untouched. They run against the in-memory SQLite `db` fixture.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks

from app.models.connection_log import ConnectionLog
from app.models.conversation import Conversation, Message
from app.routers import chat as chat_router
from app.routers import messages as messages_router
from app.schemas.chat import ChatRequest
from app.schemas.conversation import RatingUpdate
from app.services.chat import stream as turn_stream


async def _origin_answer():
    conv = await Conversation.create(status="success")
    user_msg = await Message.create(conversation=conv, role="user", content="คำถามเดิม")
    asst_msg = await Message.create(
        parent_id=user_msg.id,
        conversation=conv,
        role="assistant",
        content="คำตอบที่แคชไว้",
        sources=[{"title": "src"}],
        agency_ids=["a1"],
    )
    return conv, user_msg, asst_msg


@pytest.mark.asyncio
async def test_cache_hit_copies_into_new_conversation(db):
    conv, user_msg, asst_msg = await _origin_answer()

    with patch.object(turn_stream, "find_similar_question",
                       new=AsyncMock(return_value=(user_msg, asst_msg, MagicMock()))):
        res = await chat_router.chat(ChatRequest(query="คำถามใหม่"), BackgroundTasks(), None)

    data = res["data"]
    assert data["cached"] is True
    assert data["message_id"] != asst_msg.id
    assert res["conversation_id"] != str(conv.id)

    new = await Message.get(id=data["message_id"])
    assert new.role == "assistant"
    assert new.content == asst_msg.content
    assert str(new.conversation_id) == res["conversation_id"]
    assert new.parent_id is not None


@pytest.mark.asyncio
async def test_cache_hit_writes_a_connection_log_for_the_copy(db):
    """Cache replays go through the shared run_turn/_persist pipeline, same as a
    live turn, so a copy IS a valid future cache source (unlike the old
    `_copy_cached_answer`, which deliberately skipped logging). This pins that
    intended behavior."""
    _, user_msg, asst_msg = await _origin_answer()

    with patch.object(turn_stream, "find_similar_question",
                       new=AsyncMock(return_value=(user_msg, asst_msg, MagicMock()))):
        res = await chat_router.chat(ChatRequest(query="คำถามใหม่"), BackgroundTasks(), None)

    new_id = res["data"]["message_id"]
    assert await ConnectionLog.filter(assistant_message_id=new_id).count() >= 1


@pytest.mark.asyncio
async def test_cache_hit_rating_does_not_touch_origin(db):
    conv, user_msg, asst_msg = await _origin_answer()

    with patch.object(turn_stream, "find_similar_question",
                       new=AsyncMock(return_value=(user_msg, asst_msg, MagicMock()))):
        res = await chat_router.chat(ChatRequest(query="คำถามใหม่"), BackgroundTasks(), None)

    new_id = uuid.UUID(str(res["data"]["message_id"]))
    await messages_router.update_rating(message_id=new_id, body=RatingUpdate(rating="down"))

    assert (await Message.get(id=new_id)).rating == "down"
    assert (await Message.get(id=asst_msg.id)).rating is None
