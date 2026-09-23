"""ensure_session_warmed opens its own short-lived sessions (app.db.AsyncSessionLocal)
for the first-message lookup and the save, matching app.services.chat.stream's
short-session-per-DB-touch pattern. Bind that session factory to the test's own
connection (same pattern as test_agent_proxy_own_session.py) so writes are
visible/rolled back with `db_session`.
"""
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.conversation import Conversation, Message
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
from app.services import session as session_service
from app.services.onechat import OneChatClient

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(session_service, "AsyncSessionLocal", factory)


async def _conversation(db_session, **over) -> Conversation:
    data = dict(id=str(uuid.uuid4()), title="t", preview="p", agencies=[],
                status="success", message_count=0, response_time="0")
    data.update(over)
    conv = await conversation_repo.create(db_session, **data)
    await db_session.flush()
    return conv


async def test_warm_up_uses_chat_v3_and_stores_session_id(db_session):
    conv = await _conversation(db_session)
    await message_repo.create(db_session, id=str(uuid.uuid4()), conversation_id=conv.id,
                              role="user", content="hello")
    await db_session.flush()

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"session_id": "ext-1"}})

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await session_service.ensure_session_warmed(conv, "http://mcp", client=client)

    assert seen["url"] == "http://oc:8000/v3/chat"
    # ensure_session_warmed wrote through a different (short-lived) session;
    # db_session's identity map still holds the pre-update instance.
    await db_session.refresh(conv)
    assert conv.external_session_id == "ext-1"


async def test_warm_up_noop_when_no_first_message(db_session):
    conv = await _conversation(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await session_service.ensure_session_warmed(conv, "http://mcp", client=client)

    refreshed = await db_session.get(Conversation, conv.id)
    assert refreshed.external_session_id is None


async def test_warm_up_falls_back_to_conversation_id_when_no_session_in_response(db_session):
    conv = await _conversation(db_session)
    await message_repo.create(db_session, id=str(uuid.uuid4()), conversation_id=conv.id,
                              role="user", content="hello")
    await db_session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {}})

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await session_service.ensure_session_warmed(conv, "http://mcp", client=client)

    await db_session.refresh(conv)
    assert conv.external_session_id == str(conv.id)


async def test_warm_up_noop_when_already_warmed(db_session):
    conv = await _conversation(db_session, external_session_id="already")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await session_service.ensure_session_warmed(conv, "http://mcp", client=client)
