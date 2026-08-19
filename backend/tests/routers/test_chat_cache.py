"""Cache-hit must copy the answer into a fresh per-conversation message.

On a cache hit the endpoint previously returned the ORIGINAL message id and
conversation, so rating the answer overwrote the original message's feedback.
These tests pin the fix: a hit creates new records and leaves the original
untouched.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.connection_log import ConnectionLog
from app.models.conversation import Message
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
from app.routers import chat as chat_router
from app.schemas.chat import ChatRequest
from app.schemas.conversation import RatingUpdate
from app.services import message as message_service
from app.services.chat import stream as turn_stream

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    """_persist opens its own short-lived session; bind it to the test's
    connection so its writes are visible/rolled back with db_session."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(turn_stream, "AsyncSessionLocal", factory)


async def _origin_answer(db_session):
    conv = await conversation_repo.create(
        db_session, id=str(uuid.uuid4()), title="t", preview="p", agencies=[],
        status="success", message_count=0, response_time="0",
    )
    user_msg = await message_repo.create(
        db_session, conversation_id=conv.id, role="user", content="คำถามเดิม",
    )
    asst_msg = await message_repo.create(
        db_session,
        parent_id=user_msg.id,
        conversation_id=conv.id,
        role="assistant",
        content="คำตอบที่แคชไว้",
        sources=[{"title": "src"}],
        agency_ids=["a1"],
    )
    await db_session.flush()
    return conv, user_msg, asst_msg


async def test_cache_hit_copies_into_new_conversation(db_session):
    conv, user_msg, asst_msg = await _origin_answer(db_session)

    with patch.object(turn_stream, "find_similar_question",
                       new=AsyncMock(return_value=(user_msg, asst_msg, MagicMock()))):
        res = await chat_router.chat(ChatRequest(query="คำถามใหม่"), BackgroundTasks(), None)

    data = res["data"]
    assert data["cached"] is True
    assert data["message_id"] != asst_msg.id
    assert res["conversation_id"] != str(conv.id)

    new = await db_session.get(Message, data["message_id"])
    assert new.role == "assistant"
    assert new.content == asst_msg.content
    assert str(new.conversation_id) == res["conversation_id"]
    assert new.parent_id is not None


async def test_cache_hit_writes_a_connection_log_for_the_copy(db_session):
    """Cache replays go through the shared run_turn/_persist pipeline, same as a
    live turn, so a copy IS a valid future cache source (unlike the old
    `_copy_cached_answer`, which deliberately skipped logging). This pins that
    intended behavior."""
    _, user_msg, asst_msg = await _origin_answer(db_session)

    with patch.object(turn_stream, "find_similar_question",
                       new=AsyncMock(return_value=(user_msg, asst_msg, MagicMock()))):
        res = await chat_router.chat(ChatRequest(query="คำถามใหม่"), BackgroundTasks(), None)

    new_id = res["data"]["message_id"]
    logs = (await db_session.execute(
        select(ConnectionLog).where(ConnectionLog.assistant_message_id == new_id)
    )).scalars().all()
    assert len(logs) >= 1


async def test_cache_hit_rating_does_not_touch_origin(db_session):
    _, user_msg, asst_msg = await _origin_answer(db_session)

    with patch.object(turn_stream, "find_similar_question",
                       new=AsyncMock(return_value=(user_msg, asst_msg, MagicMock()))):
        res = await chat_router.chat(ChatRequest(query="คำถามใหม่"), BackgroundTasks(), None)

    new_id = uuid.UUID(str(res["data"]["message_id"]))
    await message_service.update_rating(db_session, new_id, RatingUpdate(rating="down"))

    assert (await db_session.get(Message, new_id)).rating == "down"
    assert (await db_session.get(Message, asst_msg.id)).rating is None
