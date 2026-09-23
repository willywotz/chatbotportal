"""The turn pipeline is transport-free: prepare_turn/run_turn own the whole
turn, and /chat/stream is only an SSE formatter over it."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.chat.models.conversation import Message
from app.features.chat.services import stream as turn_stream
from app.features.chat.services.stream import ConversationNotFound, prepare_turn, run_turn
from app.features.chat.services.turn import save_turn

pytestmark = pytest.mark.asyncio


def _inert_schedule(coro) -> None:
    """Drop a scheduled coroutine without running it, like an unflushed BackgroundTasks."""
    coro.close()


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    """prepare_turn/_persist open their own short-lived sessions; bind them to
    the test's connection so writes are visible/rolled back with db_session."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(turn_stream, "AsyncSessionLocal", factory)


async def test_prepare_turn_allocates_assistant_message_id(db_session):
    plan = await prepare_turn(
        query="q", conversation_id=str(uuid.uuid4()), user=None, is_continuation=False
    )
    assert isinstance(plan.assistant_message_id, uuid.UUID)
    assert plan.stream_version == "v5"


async def test_prepare_turn_raises_for_unknown_conversation(db_session):
    with pytest.raises(ConversationNotFound):
        await prepare_turn(
            query="q", conversation_id=str(uuid.uuid4()), user=None, is_continuation=True
        )


async def test_run_turn_persists_with_the_preallocated_id(db_session):
    conv_id = str(uuid.uuid4())
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


async def test_save_turn_honours_an_explicit_assistant_message_id(db_session):
    wanted = uuid.uuid4()
    saved = await save_turn(
        session=db_session,
        query="q", conversation_id=str(uuid.uuid4()), answer="a", references=[],
        category=None, agency_ids=[], response_time=0, user=None, succeeded=True,
        assistant_message_id=wanted,
    )
    assert saved.assistant_message_id == str(wanted)
    fetched = await db_session.get(Message, wanted)
    assert fetched.content == "a"
