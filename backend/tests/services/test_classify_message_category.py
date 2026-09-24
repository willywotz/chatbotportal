"""classify_message_category is a fire-and-forget background task (scheduled by
app.features.chat.services.stream with no session in scope), so it opens its own
short-lived session (app.core.db.AsyncSessionLocal) for the LLM call and the
category write. Bind that session factory to the test's own connection so writes
are visible/rolled back with `db_session`.
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.chat.models.conversation import Message
from app.features.chat.repositories import conversation as conversation_repo
from app.features.chat.repositories import message as message_repo
from app.features.chat.services import llm as chat_llm
from app.features.llm.services.errors import LlmError
from app.features.llm.services.result_schemas import ClassificationResult

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(chat_llm, "AsyncSessionLocal", factory)


async def _message(db_session) -> Message:
    conv = await conversation_repo.create(
        db_session, id=str(uuid.uuid4()), title="t", preview="p", agencies=[],
        status="success", message_count=0, response_time="0",
    )
    msg = await message_repo.create(
        db_session, id=str(uuid.uuid4()), conversation_id=conv.id, role="user", content="q",
    )
    await db_session.flush()
    return msg


async def test_classify_message_category_persists_category(db_session, monkeypatch):
    async def fake_parse(session, purpose, messages=None, **kw):
        return ClassificationResult(category="ขั้นตอนดำเนินการ")
    monkeypatch.setattr("app.features.llm.services.parse", fake_parse)
    msg = await _message(db_session)

    await chat_llm.classify_message_category(str(msg.id), "q", "a")

    await db_session.refresh(msg)
    assert msg.category == "ขั้นตอนดำเนินการ"


async def test_classify_message_category_swallows_llm_error(db_session, monkeypatch):
    async def fake_parse(session, purpose, messages=None, **kw):
        raise LlmError("no enabled binding", kind="config")
    monkeypatch.setattr("app.features.llm.services.parse", fake_parse)
    msg = await _message(db_session)

    await chat_llm.classify_message_category(str(msg.id), "q", "a")

    await db_session.refresh(msg)
    assert msg.category is None
