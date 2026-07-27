"""WS /chat: connection cap, cookie/bearer auth, Origin gate, query-frame round trip."""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.ws import resolve_ws_user
from app.config import settings
from app.routers import chat as chat_router
from app.services.auth_session import create_session
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent
from app.services.chat.ws import ConnectionRegistry

_ORIGIN = {"origin": settings.CORS_ORIGINS[0]}


class _FakeSocket:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}


@pytest.fixture
def restore_cap():
    original = settings.CHAT_WS_MAX_CONNECTIONS
    yield
    settings.CHAT_WS_MAX_CONNECTIONS = original


def test_registry_admits_up_to_the_cap(restore_cap):
    settings.CHAT_WS_MAX_CONNECTIONS = 2
    reg = ConnectionRegistry()
    assert reg.acquire() is True
    assert reg.acquire() is True
    assert reg.acquire() is False


def test_registry_release_never_negative(restore_cap):
    settings.CHAT_WS_MAX_CONNECTIONS = 1
    reg = ConnectionRegistry()
    reg.release()
    assert reg.acquire() is True
    assert reg.acquire() is False


@pytest.mark.asyncio
async def test_missing_authorization_is_anonymous(db):
    assert await resolve_ws_user(_FakeSocket()) is None


@pytest.fixture(autouse=True)
def _isolated_registry():
    original = chat_router._connections._open
    yield
    chat_router._connections._open = original


def _events():
    return [
        ChatEvent("answer", {"answer": "คำตอบ", "sections": [], "errors": []}),
        ChatEvent("done", {"session_id": "s", "total_ms": 1, "message_id": "m"}),
    ]


def _fake_run_turn(*events):
    async def gen(plan, *, background_tasks=None):
        for e in events:
            yield e
    return gen


def _app():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(chat_router.router, prefix="/api/v1")
    return app


def test_query_frame_round_trip(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch("app.services.chat.ws.run_turn", _fake_run_turn(*_events())), \
         TestClient(_app()) as client, \
         client.websocket_connect("/api/v1/chat", headers=_ORIGIN) as ws:
        ws.send_text(json.dumps({"query": "บัตรหาย"}))
        names = []
        while names[-1:] != ["done"]:
            names.append(json.loads(ws.receive_text())["event"])
    assert names == ["answer", "done"]


def test_malformed_frame_errors_without_closing(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch("app.services.chat.ws.run_turn", _fake_run_turn(*_events())), \
         TestClient(_app()) as client, \
         client.websocket_connect("/api/v1/chat", headers=_ORIGIN) as ws:
        ws.send_text("not json")
        first = json.loads(ws.receive_text())
        assert first["event"] == "error"
        ws.send_text(json.dumps({"query": "บัตรหาย"}))
        names = []
        while names[-1:] != ["done"]:
            names.append(json.loads(ws.receive_text())["event"])
    assert names[-1] == "done"


def test_connection_cap_refuses_next(restore_cap, db):
    settings.CHAT_WS_MAX_CONNECTIONS = 1
    with TestClient(_app()) as client:
        with client.websocket_connect("/api/v1/chat", headers=_ORIGIN):
            with pytest.raises(Exception):
                with client.websocket_connect("/api/v1/chat", headers=_ORIGIN):
                    pass


@pytest.mark.asyncio
async def test_cookie_authenticated_round_trip(db):
    from app.models.user import User

    user = await User.create(email="chatws@x.co", hashed_password="x", role="user", is_active=True)
    sid = await create_session(str(user.id))
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch("app.services.chat.ws.run_turn", _fake_run_turn(*_events())), \
         TestClient(_app()) as client:
        client.cookies.set(settings.SESSION_COOKIE_NAME, sid)
        with client.websocket_connect("/api/v1/chat", headers=_ORIGIN) as ws:
            ws.send_text(json.dumps({"query": "บัตรหาย"}))
            names = []
            while names[-1:] != ["done"]:
                names.append(json.loads(ws.receive_text())["event"])
    assert names == ["answer", "done"]


def test_disallowed_origin_is_refused(db):
    with TestClient(_app()) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/chat", headers={"origin": "https://evil.example"}):
                pass
