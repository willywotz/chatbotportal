from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tortoise import Tortoise
from contextlib import asynccontextmanager

from app.errors import register_error_handlers
from app.routers import chat as chat_router
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


def test_chat_external_calls_v3_via_client():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"answer": "A", "sections": [], "session_id": "s"}})

    fake = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    with patch.object(chat_router, "get_client", lambda: fake):
        with TestClient(_app()) as tc:
            r = tc.post("/api/v1/chat", json={"query": "hello"})
    assert r.status_code == 200
    assert r.json()["data"]["answer"] == "A"
    assert seen["url"] == "http://oc:8000/v3/chat"


def test_chat_external_upstream_error_returns_502():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    fake = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    with patch.object(chat_router, "get_client", lambda: fake):
        with TestClient(_app()) as tc:
            r = tc.post("/api/v1/chat", json={"query": "hello"})
    assert r.status_code == 502
