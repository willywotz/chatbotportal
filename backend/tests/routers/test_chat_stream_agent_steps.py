"""A streamed turn persists a pipeline snapshot into Message.agent_steps."""
import json
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.chat.models.conversation import Message
from app.features.chat.services import stream as turn_stream
from app.features.onechat.services import OneChatClient

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(turn_stream, "AsyncSessionLocal", factory)


def _stub(body: str):
    async def handler(request: httpx.Request) -> httpx.Response:
        async def gen():
            yield body.encode()
        return httpx.Response(200, content=gen())
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    return patch.object(turn_stream, "get_client", lambda version=None: client)


def _events(text: str):
    out = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        name, data = "message", None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        out.append({"event": name, "data": data})
    return out


async def test_streamed_turn_persists_agent_steps(client, db_session):
    body = (
        'event: step\ndata: {"name": "discover", "status": "done", "ms": 1200}\n\n'
        'event: agency_start\ndata: {"agency_id": "land", "agency_name": "กรมที่ดิน"}\n\n'
        'event: agency_verified\ndata: {"agency_id": "land", "status": "passed", "relevance_score": 0.9}\n\n'
        'event: answer\ndata: {"answer": "คำตอบ", "summary": "", "references": []}\n\n'
        'event: done\ndata: {"session_id": "s1", "total_ms": 42}\n\n'
    )
    with _stub(body):
        r = await client.post("/api/v1/public/chat", json={"query": "q", "stream": True})
    message_id = _events(r.text)[-1]["data"]["message_id"]

    saved = (await db_session.execute(
        select(Message).where(Message.id == message_id)
    )).scalars().one()

    assert saved.agent_steps["steps"] == [{"name": "discover", "ms": 1200}]
    assert saved.agent_steps["agencies"][0]["id"] == "land"
    assert saved.agent_steps["agencies"][0]["status"] == "passed"
