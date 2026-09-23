"""Characterization tests for chat save behavior: pins _persist's own-session
write path and save_turn's direct (caller-owned-session) write path.
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.chat.models.conversation import Conversation, Message
from app.features.chat.repositories import conversation as conversation_repo
from app.features.chat.services import stream as turn_stream
from app.features.chat.services.stream import TurnPlan, _persist
from app.features.chat.services.turn import save_turn
from app.core.utils import generate_uuid

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
    """_persist opens its own short-lived session; bind it to the test's
    connection so its writes are visible/rolled back with db_session."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(turn_stream, "AsyncSessionLocal", factory)


async def _make_conv(db_session) -> Conversation:
    conv = await conversation_repo.create(
        db_session, id=str(uuid.uuid4()), title="t", preview="p", agencies=[],
        status="success", message_count=0, response_time="0",
    )
    await db_session.flush()
    return conv


async def test_save_stream_conversation_success_status_current(db_session):
    """_persist creates a fresh conv (status=success, message_count=2) when conv does not exist."""
    cid = str(uuid.uuid4())
    assistant_id = await _persist(
        _plan(cid),
        answer_data={"answer": "hello", "sections": []},
        session_id=None,
        total_ms=10,
        latency_ms=5,
        thread_name=None,
        schedule=_inert_schedule,
    )

    conv = await db_session.get(Conversation, cid)
    assert conv.status == "success"       # CURRENT behavior — pinned
    assert conv.message_count == 2        # CURRENT behavior — pinned
    messages = (await db_session.execute(
        select(Message).where(Message.conversation_id == cid, Message.role == "assistant")
    )).scalars().all()
    assert len(messages) == 1
    assert str(assistant_id)


async def test_persist_schedules_classification_via_injected_scheduler(db_session):
    """_persist must hand the classification coroutine to the injected
    Scheduler port, not to a concrete fastapi.BackgroundTasks."""
    import asyncio

    scheduled: list = []

    def fake_schedule(coro) -> None:
        scheduled.append(coro)
        coro.close()  # never actually run it — this test only checks wiring

    cid = str(uuid.uuid4())
    await _persist(
        _plan(cid), answer_data={"answer": "a", "sections": [], "errors": []},
        session_id=None, total_ms=10, latency_ms=5, thread_name=None,
        schedule=fake_schedule,
    )

    assert len(scheduled) == 1
    assert asyncio.iscoroutine(scheduled[0])


async def test_save_turn_marks_failed_when_outcome_failed(db_session):
    cid = str(uuid.uuid4())
    res = await save_turn(
        session=db_session,
        query="q", conversation_id=cid, answer="", references=[], category=None,
        agency_ids=[], response_time=0, user=None, succeeded=False,
    )
    conv = await db_session.get(Conversation, cid)
    assert conv.status == "failed"
    assert res.assistant_message_id


async def test_save_turn_is_transactional_message_count(db_session):
    cid = str(uuid.uuid4())
    await save_turn(
        session=db_session,
        query="q", conversation_id=cid, answer="a", references=[],
        category=None, agency_ids=[], response_time=1, user=None, succeeded=True,
    )
    conv = await db_session.get(Conversation, cid)
    assert conv.status == "success"
    assert conv.message_count == 2


async def test_stream_empty_answer_marks_failed(db_session):
    """Empty answer → status=failed (documented behavior)."""
    cid = str(uuid.uuid4())
    await save_turn(
        session=db_session,
        query="q", conversation_id=cid, answer="", references=[], category=None,
        agency_ids=[], response_time=0, user=None, succeeded=False,
        external_session_id=None, errors=[],
    )
    conv = await db_session.get(Conversation, cid)
    assert conv.status == "failed"


async def test_message_stores_summary_and_summary_references(db_session):
    """Message carries the v5 executive summary and its reference list."""
    from app.features.chat.repositories import message as message_repo

    conv = await _make_conv(db_session)
    msg = await message_repo.create(
        db_session,
        conversation_id=conv.id,
        role="assistant",
        content="a",
        summary="สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]",
        summary_references=[{"number": 1, "agency_id": "land", "agency_name": "กรมที่ดิน", "url": None}],
    )
    await db_session.flush()
    fetched = await db_session.get(Message, msg.id)
    assert fetched.summary == "สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]"
    assert fetched.summary_references[0]["agency_name"] == "กรมที่ดิน"


async def test_message_summary_defaults_are_empty(db_session):
    """v4 mode and the v5 degrade path leave both fields empty, not null-ish junk."""
    from app.features.chat.repositories import message as message_repo

    conv = await _make_conv(db_session)
    msg = await message_repo.create(db_session, conversation_id=conv.id, role="assistant", content="a")
    await db_session.flush()
    fetched = await db_session.get(Message, msg.id)
    assert fetched.summary is None
    assert fetched.summary_references == []
