"""Characterization tests for chat save behavior BEFORE and AFTER the save_turn refactor.

These pin current observable behavior for unchanged paths (_persist) and assert
the NEW intended behavior for save_turn.
SQLite-portable: no external HTTP, no Postgres-only SQL.
"""
import uuid

import pytest
from fastapi import BackgroundTasks

from app.models.conversation import Conversation, Message
from app.services.chat.stream import TurnPlan, _persist
from app.utils import generate_uuid


def _plan(conv_id: str, query: str = "q") -> TurnPlan:
    return TurnPlan(
        query=query, conversation_id=conv_id, user=None, stream_version="v5",
        assistant_message_id=generate_uuid(),
    )


async def _make_conv() -> Conversation:
    return await Conversation.create(title="t", preview="p")


@pytest.mark.usefixtures("db")
async def test_save_stream_conversation_success_status_current():
    """_save_stream_conversation creates a fresh conv (status=success, message_count=2) when conv does not exist."""
    cid = str(uuid.uuid4())
    assistant_id = await _persist(
        _plan(cid),
        answer_data={"answer": "hello", "sections": []},
        session_id=None,
        total_ms=10,
        latency_ms=5,
        thread_name=None,
        background_tasks=BackgroundTasks(),
    )

    conv = await Conversation.get(id=cid)
    assert conv.status == "success"       # CURRENT behavior — pinned
    assert conv.message_count == 2        # CURRENT behavior — pinned
    assert await Message.filter(conversation_id=cid, role="assistant").count() == 1
    assert str(assistant_id)


@pytest.mark.usefixtures("db")
async def test_save_turn_marks_failed_when_outcome_failed():
    from app.services.chat.turn import save_turn
    cid = str(__import__("uuid").uuid4())
    res = await save_turn(
        query="q", conversation_id=cid, answer="", references=[], category=None,
        agency_ids=[], response_time=0, user=None, succeeded=False,
    )
    conv = await Conversation.get(id=cid)
    assert conv.status == "failed"
    assert res.assistant_message_id


@pytest.mark.usefixtures("db")
async def test_save_turn_is_transactional_message_count():
    from app.services.chat.turn import save_turn
    cid = str(__import__("uuid").uuid4())
    await save_turn(query="q", conversation_id=cid, answer="a", references=[],
                    category=None, agency_ids=[], response_time=1, user=None, succeeded=True)
    conv = await Conversation.get(id=cid)
    assert conv.status == "success"
    assert conv.message_count == 2


@pytest.mark.usefixtures("db")
async def test_stream_empty_answer_marks_failed():
    """After fold: empty answer → status=failed (documented behavior change)."""
    from app.services.chat.turn import save_turn
    cid = str(__import__("uuid").uuid4())
    await save_turn(
        query="q", conversation_id=cid, answer="", references=[], category=None,
        agency_ids=[], response_time=0, user=None, succeeded=False,
        external_session_id=None, errors=[],
    )
    conv = await Conversation.get(id=cid)
    assert conv.status == "failed"  # NEW behavior: empty answer marks failed


@pytest.mark.usefixtures("db")
async def test_message_stores_summary_and_summary_references():
    """Message carries the v5 executive summary and its reference list."""
    conv = await _make_conv()
    msg = await Message.create(
        conversation=conv,
        role="assistant",
        content="a",
        summary="สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]",
        summary_references=[{"number": 1, "agency_id": "land", "agency_name": "กรมที่ดิน", "url": None}],
    )
    fetched = await Message.get(id=msg.id)
    assert fetched.summary == "สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]"
    assert fetched.summary_references[0]["agency_name"] == "กรมที่ดิน"


@pytest.mark.usefixtures("db")
async def test_message_summary_defaults_are_empty():
    """v4 mode and the v5 degrade path leave both fields empty, not null-ish junk."""
    conv = await _make_conv()
    msg = await Message.create(conversation=conv, role="assistant", content="a")
    fetched = await Message.get(id=msg.id)
    assert fetched.summary is None
    assert fetched.summary_references == []
