"""The turn pipeline is transport-free: prepare_turn/run_turn own the whole
turn, and /chat/stream is only an SSE formatter over it."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.conversation import Conversation, Message
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ConversationNotFound, prepare_turn, run_turn


def _inert_schedule(coro) -> None:
    """Drop a scheduled coroutine without running it, like an unflushed BackgroundTasks."""
    coro.close()


@pytest.mark.asyncio
async def test_prepare_turn_allocates_assistant_message_id(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)):
        plan = await prepare_turn(
            query="q", conversation_id=str(uuid.uuid4()), user=None, is_continuation=False
        )
    assert isinstance(plan.assistant_message_id, uuid.UUID)
    assert plan.cached is None
    assert plan.stream_version == "v5"


@pytest.mark.asyncio
async def test_prepare_turn_raises_for_unknown_conversation(db):
    with pytest.raises(ConversationNotFound):
        await prepare_turn(
            query="q", conversation_id=str(uuid.uuid4()), user=None, is_continuation=True
        )


@pytest.mark.asyncio
async def test_run_turn_persists_with_the_preallocated_id(db):
    conv_id = str(uuid.uuid4())
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)):
        plan = await prepare_turn(
            query="q", conversation_id=conv_id, user=None, is_continuation=False
        )

    async def fake_stream(plan_arg, schedule):
        yield turn_stream.ChatEvent("step", {"name": "summarize"})
        yield turn_stream.ChatEvent("answer", {"answer": "คำตอบ", "sections": [], "errors": []})
        yield turn_stream.ChatEvent("done", {"session_id": conv_id, "total_ms": 12})

    with patch.object(turn_stream, "_stream_live", new=fake_stream):
        names = [ev.name async for ev in run_turn(plan, schedule=_inert_schedule)]

    assert names == ["step", "answer", "done"]


@pytest.mark.asyncio
async def test_run_turn_replays_a_cache_hit(db):
    conv = await Conversation.create(status="success")
    user_msg = await Message.create(conversation=conv, role="user", content="q")
    asst_msg = await Message.create(
        parent_id=user_msg.id, conversation=conv, role="assistant", content="cached answer"
    )
    conn_log = MagicMock(response_body=json.dumps({"answer": "cached answer"}))

    with patch.object(
        turn_stream, "find_similar_question",
        new=AsyncMock(return_value=(user_msg, asst_msg, conn_log)),
    ):
        plan = await prepare_turn(
            query="q", conversation_id=str(uuid.uuid4()), user=None, is_continuation=False
        )
    assert plan.cached is not None

    events = [ev async for ev in run_turn(plan, schedule=_inert_schedule)]
    assert [e.name for e in events] == ["answer", "done"]
    assert events[0].data["answer"] == "cached answer"
    assert events[1].data["message_id"] == str(plan.assistant_message_id)


@pytest.mark.asyncio
async def test_save_turn_honours_an_explicit_assistant_message_id(db):
    from app.services.chat.turn import save_turn

    wanted = uuid.uuid4()
    saved = await save_turn(
        query="q", conversation_id=str(uuid.uuid4()), answer="a", references=[],
        category=None, agency_ids=[], response_time=0, user=None, succeeded=True,
        assistant_message_id=wanted,
    )
    assert saved.assistant_message_id == str(wanted)
    assert (await Message.get(id=wanted)).content == "a"
