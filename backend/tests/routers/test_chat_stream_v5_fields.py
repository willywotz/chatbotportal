"""v5 `answer` event fields land on the assistant message.

`summary` and `references` are scoped to the executive summary; `sources` keeps
its legacy section-derived meaning and stays empty on the stream path.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.conversation import Conversation, Message
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
from app.routers import chat as chat_router
from app.schemas.chat import ChatRequest
from app.services.chat import stream as turn_stream
from app.services.chat.stream import TurnPlan, _persist
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


V5_ANSWER = {
    "answer": "สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]\n\n---\n\n## ค่าธรรมเนียม\n\nค่าธรรมเนียมการโอนคือ 2%",
    "summary": "สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]",
    "references": [{"number": 1, "agency_id": "land", "agency_name": "กรมที่ดิน", "url": None}],
    "sections": [{"title": "ค่าธรรมเนียม", "agencies": [{"id": "land", "name": "กรมที่ดิน", "query": "q", "content": "c"}]}],
    "errors": [],
}


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


async def test_stream_persists_summary_and_references(db_session):
    cid = str(uuid.uuid4())
    asst_id = await _persist(
        _plan(cid), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5, thread_name=None,
        schedule=_inert_schedule,
    )
    msg = await db_session.get(Message, asst_id)
    assert msg.summary == "สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]"
    assert msg.summary_references == [
        {"number": 1, "agency_id": "land", "agency_name": "กรมที่ดิน", "url": None}
    ]
    assert msg.sources == []
    assert msg.agency_ids == ["land"]


async def test_stream_degrades_silently_without_summary(db_session):
    cid = str(uuid.uuid4())
    asst_id = await _persist(
        _plan(cid), answer_data={"answer": "คำตอบ", "sections": [], "errors": []},
        session_id=None, total_ms=10, latency_ms=5, thread_name=None,
        schedule=_inert_schedule,
    )
    msg = await db_session.get(Message, asst_id)
    assert msg.summary is None
    assert msg.summary_references == []
    assert msg.content == "คำตอบ"


async def test_blank_summary_is_stored_as_none(db_session):
    """Spec §4.3: a failed summary arrives as "" — do not store an empty string."""
    cid = str(uuid.uuid4())
    asst_id = await _persist(
        _plan(cid),
        answer_data={"answer": "คำตอบ", "summary": "   ", "references": [], "sections": [], "errors": []},
        session_id=None, total_ms=10, latency_ms=5, thread_name=None,
        schedule=_inert_schedule,
    )
    msg = await db_session.get(Message, asst_id)
    assert msg.summary is None


async def test_thread_name_titles_a_new_conversation(db_session):
    cid = str(uuid.uuid4())
    await _persist(
        _plan(cid, query="ค่าธรรมเนียมโอนที่ดินเท่าไหร่ ช่วยอธิบายละเอียดหน่อยครับ"),
        answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name="ค่าธรรมเนียมโอนที่ดิน", schedule=_inert_schedule,
    )
    conv = await db_session.get(Conversation, cid)
    assert conv.title == "ค่าธรรมเนียมโอนที่ดิน"


async def test_null_thread_name_keeps_query_derived_title(db_session):
    cid = str(uuid.uuid4())
    await _persist(
        _plan(cid, query="ค่าธรรมเนียมโอนที่ดินเท่าไหร่"), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name=None, schedule=_inert_schedule,
    )
    conv = await db_session.get(Conversation, cid)
    assert conv.title == "ค่าธรรมเนียมโอนที่ดินเท่าไหร่"


async def test_thread_name_does_not_retitle_an_existing_conversation(db_session):
    """Turn 2+ must never rename the thread mid-conversation (spec §4.5)."""
    cid = str(uuid.uuid4())
    await _persist(
        _plan(cid, query="q1"), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name="ชื่อเดิม", schedule=_inert_schedule,
    )
    await _persist(
        _plan(cid, query="q2"), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name="ชื่อใหม่", schedule=_inert_schedule,
    )
    conv = await db_session.get(Conversation, cid)
    assert conv.title == "ชื่อเดิม"


async def test_long_thread_name_is_truncated(db_session):
    cid = str(uuid.uuid4())
    await _persist(
        _plan(cid), answer_data=V5_ANSWER,
        session_id=None, total_ms=10, latency_ms=5,
        thread_name="ก" * 200, schedule=_inert_schedule,
    )
    conv = await db_session.get(Conversation, cid)
    assert len(conv.title) == settings.TITLE_MAX_LENGTH


async def test_cached_replay_emits_summary_and_references(db_session):
    conv = await conversation_repo.create(
        db_session, id=str(uuid.uuid4()), title="t", preview="p", agencies=[],
        status="success", message_count=0, response_time="0",
    )
    user_msg = await message_repo.create(
        db_session, conversation_id=conv.id, role="user", content="q",
    )
    asst_msg = await message_repo.create(
        db_session, parent_id=user_msg.id, conversation_id=conv.id, role="assistant",
        content=V5_ANSWER["answer"],
        summary=V5_ANSWER["summary"],
        summary_references=V5_ANSWER["references"],
    )
    await db_session.flush()
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
