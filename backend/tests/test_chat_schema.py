"""
Verify that the OpenAPI schema exposes only the canonical chat surface
(/chat) and hides the internal/external variants.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.chat import router as chat_router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat_router, prefix="/api/v1")
    return app


def test_openapi_hides_internal_chat_variants():
    schema = TestClient(_app()).get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/stream" not in paths
    assert "/api/v1/chat/external" not in paths
    assert "/api/v1/chat/internal" not in paths


def test_internal_chat_route_is_removed():
    """The LangGraph /chat/internal endpoint is fully removed (not just hidden)."""
    assert not any(getattr(r, "path", "") == "/chat/internal" for r in chat_router.routes)
    from app.routers import chat as chat_module
    assert not hasattr(chat_module, "chat_internal")


from app.schemas.chat import ChatRequest


def test_chat_request_stream_and_model_defaults():
    r = ChatRequest(query="q")
    assert r.stream is False
    assert r.model is None
    r2 = ChatRequest(query="q", stream=True, model="onechat-v3")
    assert r2.stream is True
    assert r2.model == "onechat-v3"
