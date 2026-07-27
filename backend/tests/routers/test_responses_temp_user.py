"""POST /api/v1/responses requires an authenticated caller (no ephemeral users)."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.auth.security import generate_api_key, hash_api_key, hash_password
from app.errors import register_error_handlers
from app.models.user import User, UserAPIKey
from app.routers import responses as responses_router
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent

from .test_responses_http import _fake_live, ANSWER_DATA

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


def _client_app() -> FastAPI:
    app = FastAPI(lifespan=_lifespan)
    register_error_handlers(app)
    app.include_router(responses_router.router, prefix="/api/v1")
    return app


def _default_events(conversation_id: str = "s"):
    return (
        ChatEvent("step", {"name": "summarize"}),
        ChatEvent("answer", ANSWER_DATA),
        ChatEvent("done", {"session_id": conversation_id, "total_ms": 900}),
    )


async def _api_key_headers(email: str) -> dict:
    user = await User.create(email=email, hashed_password=hash_password("pw"))
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    return {"Authorization": f"Bearer {raw}"}


async def test_anonymous_create_is_401():
    app = _client_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/v1/responses", json={"input": "hi"})

    assert r.status_code == 401


async def test_authenticated_create_has_no_session_header():
    app = _client_app()
    async with app.router.lifespan_context(app):
        headers = await _api_key_headers("real@x.y")
        with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
             patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                r = await c.post("/api/v1/responses", json={"input": "hi"}, headers=headers)

    assert r.status_code == 200
    assert "X-Portal-Session" not in r.headers


async def test_thai_text_not_ascii_escaped():
    app = _client_app()
    async with app.router.lifespan_context(app):
        headers = await _api_key_headers("thai@x.y")
        with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
             patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                r = await c.post("/api/v1/responses", json={"input": "hi"}, headers=headers)

    assert r.status_code == 200
    assert "คำตอบเต็ม" in r.text
    assert "\\u" not in r.text
