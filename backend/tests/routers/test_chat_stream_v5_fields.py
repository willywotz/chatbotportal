"""v5 `answer` event fields land on the assistant message.

`summary` and `references` are scoped to the executive summary; `sources` keeps
its legacy section-derived meaning and stays empty on the stream path.
"""

import uuid

import pytest
from fastapi import BackgroundTasks

from app.models.conversation import Message
from app.services.chat.stream import TurnPlan, _persist
from app.utils import generate_uuid


def _plan(conv_id: str, query: str = "q") -> TurnPlan:
    return TurnPlan(
        query=query, conversation_id=conv_id, user=None, stream_version="v5",
        assistant_message_id=generate_uuid(),
    )

V5_ANSWER = {
    "answer": "สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]\n\n---\n\n## ค่าธรรมเนียม\n\nค่าธรรมเนียมการโอนคือ 2%",
    "summary": "สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]",
    "references": [{"number": 1, "agency_id": "land", "agency_name": "กรมที่ดิน", "url": None}],
    "sections": [{"title": "ค่าธรรมเนียม", "agencies": [{"id": "land", "name": "กรมที่ดิน", "query": "q", "content": "c"}]}],
    "errors": [],
}


@pytest.mark.usefixtures("db")
async def test_stream_persists_summary_and_references():
    cid = str(uuid.uuid4())
    asst_id = await _persist(
        _plan(cid), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5, thread_name=None,
        background_tasks=BackgroundTasks(),
    )
    msg = await Message.get(id=asst_id)
    assert msg.summary == "สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]"
    assert msg.summary_references == [
        {"number": 1, "agency_id": "land", "agency_name": "กรมที่ดิน", "url": None}
    ]
    assert msg.sources == []
    assert msg.agency_ids == ["land"]


@pytest.mark.usefixtures("db")
async def test_stream_degrades_silently_without_summary():
    """v4 mode / upstream summary failure: empty fields, everything else unchanged."""
    cid = str(uuid.uuid4())
    asst_id = await _persist(
        _plan(cid), answer_data={"answer": "คำตอบ", "sections": [], "errors": []},
        session_id=None, total_ms=10, latency_ms=5, thread_name=None,
        background_tasks=BackgroundTasks(),
    )
    msg = await Message.get(id=asst_id)
    assert msg.summary is None
    assert msg.summary_references == []
    assert msg.content == "คำตอบ"


@pytest.mark.usefixtures("db")
async def test_blank_summary_is_stored_as_none():
    """Spec §4.3: a failed summary arrives as "" — do not store an empty string."""
    cid = str(uuid.uuid4())
    asst_id = await _persist(
        _plan(cid),
        answer_data={"answer": "คำตอบ", "summary": "   ", "references": [], "sections": [], "errors": []},
        session_id=None, total_ms=10, latency_ms=5, thread_name=None,
        background_tasks=BackgroundTasks(),
    )
    msg = await Message.get(id=asst_id)
    assert msg.summary is None


# ─── thread_name → conversation title ────────────────────────────────────────

from app.config import settings
from app.models.conversation import Conversation


@pytest.mark.usefixtures("db")
async def test_thread_name_titles_a_new_conversation():
    cid = str(uuid.uuid4())
    await _persist(
        _plan(cid, query="ค่าธรรมเนียมโอนที่ดินเท่าไหร่ ช่วยอธิบายละเอียดหน่อยครับ"),
        answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name="ค่าธรรมเนียมโอนที่ดิน", background_tasks=BackgroundTasks(),
    )
    conv = await Conversation.get(id=cid)
    assert conv.title == "ค่าธรรมเนียมโอนที่ดิน"


@pytest.mark.usefixtures("db")
async def test_null_thread_name_keeps_query_derived_title():
    cid = str(uuid.uuid4())
    await _persist(
        _plan(cid, query="ค่าธรรมเนียมโอนที่ดินเท่าไหร่"), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name=None, background_tasks=BackgroundTasks(),
    )
    conv = await Conversation.get(id=cid)
    assert conv.title == "ค่าธรรมเนียมโอนที่ดินเท่าไหร่"


@pytest.mark.usefixtures("db")
async def test_thread_name_does_not_retitle_an_existing_conversation():
    """Turn 2+ must never rename the thread mid-conversation (spec §4.5)."""
    cid = str(uuid.uuid4())
    await _persist(
        _plan(cid, query="q1"), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name="ชื่อเดิม", background_tasks=BackgroundTasks(),
    )
    await _persist(
        _plan(cid, query="q2"), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name="ชื่อใหม่", background_tasks=BackgroundTasks(),
    )
    conv = await Conversation.get(id=cid)
    assert conv.title == "ชื่อเดิม"


@pytest.mark.usefixtures("db")
async def test_long_thread_name_is_truncated():
    cid = str(uuid.uuid4())
    await _persist(
        _plan(cid), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name="ก" * 200, background_tasks=BackgroundTasks(),
    )
    conv = await Conversation.get(id=cid)
    assert len(conv.title) == settings.TITLE_MAX_LENGTH


# ─── similarity-cache replay ─────────────────────────────────────────────────

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers import chat as chat_router
from app.schemas.chat import ChatRequest
from app.services.chat import stream as turn_stream


@pytest.mark.usefixtures("db")
async def test_cached_replay_emits_summary_and_references():
    """A cache hit must look identical to a live v5 turn."""
    conv = await Conversation.create(status="success")
    user_msg = await Message.create(conversation=conv, role="user", content="q")
    asst_msg = await Message.create(
        parent_id=user_msg.id, conversation=conv, role="assistant",
        content=V5_ANSWER["answer"],
        summary=V5_ANSWER["summary"],
        summary_references=V5_ANSWER["references"],
    )
    conn_log = MagicMock(response_body=json.dumps(V5_ANSWER, ensure_ascii=False))

    with patch.object(turn_stream, "find_similar_question",
                      new=AsyncMock(return_value=(user_msg, asst_msg, conn_log))):
        resp = await chat_router.chat(ChatRequest(query="q", stream=True), BackgroundTasks(), None)
        chunks = [c async for c in resp.body_iterator]

    text = "".join(c if isinstance(c, str) else c.decode() for c in chunks)
    answer_block = next(b for b in text.split("\n\n") if b.startswith("event: answer"))
    payload = json.loads(answer_block.split("data: ", 1)[1])
    assert payload["summary"] == V5_ANSWER["summary"]
    assert payload["references"] == V5_ANSWER["references"]
