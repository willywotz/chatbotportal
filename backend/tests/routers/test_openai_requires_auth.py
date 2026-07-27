"""/responses and /conversations require an authenticated caller (no ephemeral users)."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from tortoise import Tortoise

from app.auth.dependencies import enforce_role_allowlist
from app.errors import register_error_handlers
from app.routers import openai_conversations, responses as responses_router


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


def _app() -> FastAPI:
    app = FastAPI(lifespan=_lifespan, dependencies=[Depends(enforce_role_allowlist)])
    register_error_handlers(app)
    app.include_router(responses_router.router, prefix="/api/v1")
    app.include_router(openai_conversations.router, prefix="/api/v1")
    return app


def test_responses_anonymous_is_401(db):
    with TestClient(_app()) as client:
        r = client.post("/api/v1/responses", json={"model": "onechat", "input": "hi"})
    assert r.status_code == 401


def test_conversations_anonymous_is_401(db):
    with TestClient(_app()) as client:
        r = client.post("/api/v1/conversations", json={})
    assert r.status_code == 401
