"""The chat stream must never pin one DB transaction for the whole SSE/WS
turn: the similarity-cache read, the conversation lookup, and the end-of-turn
persistence each open their own short-lived session (app.db.AsyncSessionLocal).

These tests bind that short-lived session factory to the test's own connection
(same pattern as test_rate_limit.py/test_outbox_transactional.py) so writes are
visible through `db_session` and rolled back with it.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.connection_log import ConnectionLog
from app.models.conversation import Conversation, Message
from app.repositories import conversation as conversation_repo
from app.services.chat import stream as turn_stream
from app.services.chat.stream import TurnPlan, _persist, prepare_turn
from app.utils import generate_uuid

pytestmark = pytest.mark.asyncio


async def _bind_own_session(db_session, monkeypatch) -> None:
    """Point stream.py's AsyncSessionLocal at the test's own connection so its
    short-lived sessions write into (and roll back with) `db_session`."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(turn_stream, "AsyncSessionLocal", factory)


def _inert_schedule(coro) -> None:
    coro.close()


def _plan(conv_id: str, query: str = "q") -> TurnPlan:
    return TurnPlan(
        query=query, conversation_id=conv_id, user=None, stream_version="v5",
        assistant_message_id=generate_uuid(),
    )


async def test_prepare_turn_similarity_read_runs_in_its_own_session(db_session, monkeypatch):
    """Non-continuation prepare_turn opens a short read session for
    find_similar_question and never touches it again."""
    await _bind_own_session(db_session, monkeypatch)

    plan = await prepare_turn(
        query="hello", conversation_id=str(uuid.uuid4()), user=None, is_continuation=False,
    )
    assert plan.cached is None  # empty DB: no similarity match, no error


async def test_prepare_turn_continuation_looks_up_conversation_in_its_own_session(
    db_session, monkeypatch,
):
    """The continuation branch's conversation_repo.by_id call uses the same
    short-session pattern, not a bare Tortoise-style call."""
    await _bind_own_session(db_session, monkeypatch)

    conv = await conversation_repo.create(
        db_session, id=str(uuid.uuid4()), title="t", preview="p", agencies=[],
        status="success", message_count=0, response_time="0",
    )
    await db_session.flush()

    with patch.object(turn_stream, "ensure_session_warmed", new=AsyncMock(return_value=None)):
        plan = await prepare_turn(
            query="q", conversation_id=conv.id, user=None, is_continuation=True,
        )
    assert plan.conversation_id == conv.id


async def test_persist_writes_turn_and_connection_log_via_one_short_session(
    db_session, monkeypatch,
):
    """A completed turn's save_turn + ConnectionLog.create land in the same
    short-lived session (not the caller's/request session)."""
    await _bind_own_session(db_session, monkeypatch)

    conv_id = str(uuid.uuid4())
    plan = _plan(conv_id)

    assistant_id = await _persist(
        plan, answer_data={"answer": "hello", "sections": []}, session_id=None,
        total_ms=10, latency_ms=5, thread_name=None, schedule=_inert_schedule,
    )

    conv = await db_session.get(Conversation, conv_id)
    assert conv is not None
    assert conv.status == "success"
    assert conv.message_count == 2

    messages = (
        await db_session.execute(select(Message).where(Message.conversation_id == conv_id))
    ).scalars().all()
    assert len(messages) == 2

    logs = (
        await db_session.execute(
            select(ConnectionLog).where(ConnectionLog.assistant_message_id == str(assistant_id))
        )
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].action == "query"
    assert logs[0].status == "success"


async def test_persist_schedules_classification_after_the_session_closes(db_session, monkeypatch):
    await _bind_own_session(db_session, monkeypatch)

    scheduled: list = []

    def fake_schedule(coro) -> None:
        scheduled.append(coro)
        coro.close()

    await _persist(
        _plan(str(uuid.uuid4())), answer_data={"answer": "a", "sections": [], "errors": []},
        session_id=None, total_ms=10, latency_ms=5, thread_name=None, schedule=fake_schedule,
    )
    assert len(scheduled) == 1
