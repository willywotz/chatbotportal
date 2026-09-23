"""POST /api/v1/public/chat against a stubbed OneChat upstream.

Every other test in the suite patches `_stream_live` out entirely, so the code
that talks to the real upstream — non-200 handling, SSE reassembly across chunk
boundaries, `ReadTimeout`, and the generic-exception branch — is asserted by
nothing. These tests drive the real ASGI stack (via the `client` fixture) with
an `OneChatClient` whose `httpx.MockTransport` serves canned SSE, so
`_stream_live` runs for real while no network call happens.

Characterization tests: they assert what the code does today, not what it
should do. Behaviour preservation is the whole point of this file.
"""

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
    """The stream pipeline persists via its own short-lived session; bind it
    to the test's connection so the saved message is visible through db_session."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(turn_stream, "AsyncSessionLocal", factory)


def _mock_client(*, status: int = 200, chunks: tuple[str, ...] = (), exc: Exception | None = None):
    """An OneChatClient whose MockTransport serves the given SSE chunks.

    `chunks` are delivered as distinct byte reads so `_stream_live`'s SSE
    reassembly across chunk boundaries is exercised end to end.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        if exc is not None:
            raise exc

        async def body():
            for chunk in chunks:
                yield chunk.encode()

        return httpx.Response(status, content=body())

    return OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))


def _stub_upstream(*, status: int = 200, chunks: tuple[str, ...] = (), exc: Exception | None = None):
    client = _mock_client(status=status, chunks=chunks, exc=exc)
    return patch.object(turn_stream, "get_client", lambda version=None: client)


def _events(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name, data = "message", None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        events.append({"event": event_name, "data": data})
    return events


async def test_happy_path_streams_step_answer_and_done(client, db_session):
    body = (
        'event: step\ndata: {"name": "summarize"}\n\n'
        'event: answer\ndata: {"answer": "คำตอบ", "summary": "", "references": []}\n\n'
        'event: done\ndata: {"session_id": "s1", "total_ms": 42}\n\n'
    )
    with _stub_upstream(status=200, chunks=(body,)):
        r = await client.post("/api/v1/public/chat", json={"query": "บัตรหาย", "stream": True})
    assert r.status_code == 200
    events = _events(r.text)
    assert [e["event"] for e in events] == ["step", "answer", "done"]
    assert events[1]["data"]["answer"] == "คำตอบ"
    assert "message_id" in events[2]["data"]

    message_id = events[2]["data"]["message_id"]
    saved = (await db_session.execute(
        select(Message).where(Message.id == message_id)
    )).scalars().one()
    assert saved.role == "assistant"
    assert saved.content == "คำตอบ"


async def test_sse_reassembly_across_chunk_boundaries(client):
    full = (
        'event: answer\ndata: {"answer": "OK", "summary": "", "references": []}\n\n'
        'event: done\ndata: {"session_id": "s1", "total_ms": 1}\n\n'
    )
    cut1 = full.index("event: answer") + len("event: ans")  # mid `event:` line
    cut2 = full.index('"answer":') + len('"answ')  # mid-JSON key
    chunks = (full[:cut1], full[cut1:cut2], full[cut2:])

    with _stub_upstream(status=200, chunks=chunks):
        r = await client.post("/api/v1/public/chat", json={"query": "q", "stream": True})
    events = _events(r.text)
    assert [e["event"] for e in events] == ["answer", "done"]
    assert events[0]["data"]["answer"] == "OK"


async def test_upstream_non_200_emits_error_then_done(client):
    with _stub_upstream(status=502, chunks=()):
        r = await client.post("/api/v1/public/chat", json={"query": "q", "stream": True})
    events = _events(r.text)
    assert [e["event"] for e in events] == ["error", "done"]
    assert events[0]["data"]["code"] == 502


async def test_read_timeout_emits_error_then_done(client):
    with _stub_upstream(exc=httpx.ReadTimeout("timed out")):
        r = await client.post("/api/v1/public/chat", json={"query": "q", "stream": True})
    events = _events(r.text)
    assert [e["event"] for e in events] == ["error", "done"]
    assert "timed out" in events[0]["data"]["message"]


async def test_stream_version_uses_resolver_default():
    assert turn_stream._stream_version() == "v5"
