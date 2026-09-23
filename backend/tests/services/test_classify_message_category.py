"""classify_message_category is a fire-and-forget background task (scheduled by
app.services.chat.stream with no session in scope), so it opens its own
short-lived session (app.db.AsyncSessionLocal) for the LLM call and the
category write. Bind that session factory to the test's own connection (same
pattern as test_agent_proxy_own_session.py) so writes are visible/rolled back
with `db_session`.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.conversation import Message
from app.repositories import conversation as conversation_repo
from app.repositories import llm as llm_repo
from app.repositories import message as message_repo
from app.services.chat import llm as chat_llm
from app.services.llm import client as llm_client

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(chat_llm, "AsyncSessionLocal", factory)


def _mock_httpx(json_body, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body
    resp.text = "body"
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


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


async def test_classify_message_category_persists_category(db_session):
    llm_client.invalidate()
    provider = await llm_repo.create_provider(db_session, name="p", base_url="u", api_key="k")
    await llm_repo.create_route(db_session, purpose="classification", provider_id=provider.id, model="m")
    msg = await _message(db_session)

    body = {"model": "m", "choices": [{"message": {"content": "ขั้นตอนดำเนินการ"}}]}
    with patch.object(llm_client.httpx, "AsyncClient", _mock_httpx(body)):
        await chat_llm.classify_message_category(str(msg.id), "q", "a")

    await db_session.refresh(msg)
    assert msg.category == "ขั้นตอนดำเนินการ"


async def test_classify_message_category_swallows_llm_error(db_session):
    llm_client.invalidate()
    # No route configured for "classification" -> LlmError from _resolve.
    msg = await _message(db_session)

    await chat_llm.classify_message_category(str(msg.id), "q", "a")

    await db_session.refresh(msg)
    assert msg.category is None
