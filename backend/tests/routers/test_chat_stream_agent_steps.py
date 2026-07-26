"""A streamed turn persists a pipeline snapshot into Message.agent_steps."""
import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tortoise import Tortoise
from unittest.mock import patch

from app.errors import register_error_handlers
from app.models.conversation import Message
from app.routers import chat as chat_router
from app.services.chat import stream as turn_stream
from app.services.onechat import OneChatClient


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


def _app() -> FastAPI:
    app = FastAPI(lifespan=_lifespan)
    register_error_handlers(app)
    app.include_router(chat_router.router, prefix="/api/v1")
    return app


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


def test_streamed_turn_persists_agent_steps():
    body = (
        'event: step\ndata: {"name": "discover", "status": "done", "ms": 1200}\n\n'
        'event: agency_start\ndata: {"agency_id": "land", "agency_name": "กรมที่ดิน"}\n\n'
        'event: agency_verified\ndata: {"agency_id": "land", "status": "passed", "relevance_score": 0.9}\n\n'
        'event: answer\ndata: {"answer": "คำตอบ", "summary": "", "references": []}\n\n'
        'event: done\ndata: {"session_id": "s1", "total_ms": 42}\n\n'
    )
    with _stub(body), TestClient(_app()) as client:
        r = client.post("/api/v1/chat/stream", json={"query": "q"})
        message_id = _events(r.text)[-1]["data"]["message_id"]

        async def _fetch():
            return await Message.get(id=message_id)

        saved = client.portal.call(_fetch)

    assert saved.agent_steps["steps"] == [{"name": "discover", "ms": 1200}]
    assert saved.agent_steps["agencies"][0]["id"] == "land"
    assert saved.agent_steps["agencies"][0]["status"] == "passed"
