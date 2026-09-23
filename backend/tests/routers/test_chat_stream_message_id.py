"""Streaming must expose the real DB assistant message id for feedback.

`_persist` returns the new assistant id, and the `done` SSE event carries it
as `message_id`, so a streamed answer can be rated against a real row instead
of a client-generated id.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from opentelemetry.trace import StatusCode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.conversation import Message
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
from app.routers import chat as chat_router
from app.schemas.chat import ChatRequest
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent, TurnPlan, _persist
from app.utils import generate_uuid

pytestmark = pytest.mark.asyncio


def _plan(conv_id: str, query: str = "q") -> TurnPlan:
    return TurnPlan(
        query=query, conversation_id=conv_id, user=None, stream_version="v5",
        assistant_message_id=generate_uuid(),
    )


def _inert_schedule(coro) -> None:
    """Drop a scheduled coroutine without running it, like an unflushed BackgroundTasks."""
    coro.close()


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    """_persist/prepare_turn open their own short-lived sessions; bind them to
    the test's connection so writes are visible/rolled back with db_session."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(turn_stream, "AsyncSessionLocal", factory)


async def test_save_stream_conversation_returns_assistant_id(db_session):
    conv_id = str(uuid.uuid4())
    asst_id = await _persist(
        _plan(conv_id),
        answer_data={"answer": "คำตอบ", "errors": [], "sections": []},
        session_id=None,
        total_ms=0,
        latency_ms=0,
        thread_name=None,
        schedule=_inert_schedule,
    )
    saved = await db_session.get(Message, asst_id)
    assert saved.role == "assistant"
    assert saved.content == "คำตอบ"


async def test_cached_stream_emits_message_id_in_done(db_session):
    conv = await conversation_repo.create(
        db_session, id=str(uuid.uuid4()), title="t", preview="p", agencies=[],
        status="success", message_count=0, response_time="0",
    )
    user_msg = await message_repo.create(
        db_session, conversation_id=conv.id, role="user", content="q",
    )
    asst_msg = await message_repo.create(
        db_session, parent_id=user_msg.id, conversation_id=conv.id, role="assistant",
        content="cached answer",
    )
    await db_session.flush()
    conn_log = MagicMock(response_body=json.dumps({"answer": "cached answer"}))

    with patch.object(turn_stream, "find_similar_question",
                      new=AsyncMock(return_value=(user_msg, asst_msg, conn_log))):
        resp = await chat_router.chat(ChatRequest(query="q", stream=True), BackgroundTasks(), None)
        chunks = [c async for c in resp.body_iterator]

    text = "".join(c if isinstance(c, str) else c.decode() for c in chunks)
    new_asst = (await db_session.execute(
        select(Message).where(Message.role == "assistant", Message.id != asst_msg.id)
    )).scalars().first()
    assert new_asst is not None
    assert "event: done" in text
    assert str(new_asst.id) in text


async def test_error_event_marks_endpoint_span_as_error(db_session):
    """The endpoint span must be marked ERROR on upstream failure (pre-refactor behavior)."""

    async def fake_run_turn(plan, *, schedule=None):
        yield ChatEvent("error", {"message": "OneChat v5 returned 502", "code": 502})
        yield ChatEvent("done", {"session_id": plan.conversation_id, "total_ms": 0})

    mock_span = MagicMock()
    mock_span_cm = MagicMock()
    mock_span_cm.__enter__.return_value = mock_span

    with patch.object(chat_router, "run_turn", fake_run_turn), \
         patch.object(chat_router.tracer, "start_as_current_span", return_value=mock_span_cm):
        resp = await chat_router.chat(ChatRequest(query="q", stream=True), BackgroundTasks(), None)
        [c async for c in resp.body_iterator]

    mock_span.set_status.assert_any_call(StatusCode.ERROR, "OneChat v5 returned 502")
