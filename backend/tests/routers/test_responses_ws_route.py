"""The socket loop: connection cap, auth resolution, duration cap."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket

from app.config import settings
from app.routers import responses as responses_router
from app.routers.responses import _ConnectionRegistry, _ws_user
from app.services.chat import stream as turn_stream
from app.services.onechat import OneChatClient
from tests.routers.test_responses_http import _client_app, _default_events, _fake_live


@pytest.fixture
def restore_cap():
    original = settings.RESPONSES_WS_MAX_CONNECTIONS
    yield
    settings.RESPONSES_WS_MAX_CONNECTIONS = original


class _FakeSocket:
    def __init__(self, headers: dict[str, str] | None = None):
        self.headers = headers or {}


def test_registry_admits_up_to_the_cap(restore_cap):
    settings.RESPONSES_WS_MAX_CONNECTIONS = 2
    registry = _ConnectionRegistry()
    assert registry.acquire() is True
    assert registry.acquire() is True
    assert registry.acquire() is False


def test_registry_frees_a_slot_on_release(restore_cap):
    settings.RESPONSES_WS_MAX_CONNECTIONS = 1
    registry = _ConnectionRegistry()
    assert registry.acquire() is True
    assert registry.acquire() is False
    registry.release()
    assert registry.acquire() is True


def test_release_never_goes_negative(restore_cap):
    settings.RESPONSES_WS_MAX_CONNECTIONS = 1
    registry = _ConnectionRegistry()
    registry.release()
    registry.release()
    assert registry.acquire() is True
    assert registry.acquire() is False


@pytest.mark.asyncio
async def test_missing_authorization_is_anonymous(db):
    assert await _ws_user(_FakeSocket()) is None


@pytest.mark.asyncio
async def test_non_bearer_authorization_is_anonymous(db):
    assert await _ws_user(_FakeSocket({"authorization": "Basic abc"})) is None


@pytest.mark.asyncio
async def test_invalid_token_is_anonymous_not_an_exception(db):
    assert await _ws_user(_FakeSocket({"authorization": "Bearer tcg_bogus"})) is None


# ─── End-to-end: a real socket through TestClient.websocket_connect ──────────


@pytest.fixture(autouse=True)
def _isolated_connection_registry():
    """`_connections` is module-level state shared across every test module.

    Snapshot and restore its count so a test that leaves the registry non-zero
    (e.g. the leak regression below, before the fix) cannot bleed into other
    tests' assertions.
    """
    original = responses_router._connections._open
    yield
    responses_router._connections._open = original


def test_response_create_round_trip_over_a_real_socket():
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))), \
         TestClient(_client_app()) as client, \
         client.websocket_connect("/api/v1/responses") as ws:
        ws.send_text(json.dumps({
            "type": "response.create", "model": "onechat", "input": "บัตรหาย",
        }))
        types = []
        while types[-1:] != ["response.completed"] and types[-1:] != ["response.failed"]:
            types.append(json.loads(ws.receive_text())["type"])

    assert types == [
        "response.created", "response.output_item.added", "response.content_part.added",
        "response.output_text.delta", "response.output_text.done",
        "response.content_part.done", "response.output_item.done", "response.completed",
    ]


def test_response_create_onechat_version_routes_to_v3():
    """`onechat_version` on a response.create frame overrides the resolved upstream."""
    rec: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        rec["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"answer": "ok", "session_id": "s1"}})

    def stub_client(version: str | None = None) -> OneChatClient:
        return OneChatClient(
            "http://oc:8000", transport=httpx.MockTransport(handler), version=version,
        )

    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "get_client", stub_client), \
         TestClient(_client_app()) as client, \
         client.websocket_connect("/api/v1/responses") as ws:
        ws.send_text(json.dumps({
            "type": "response.create", "model": "onechat", "onechat_version": "v3",
            "input": "บัตรหาย",
        }))
        types = []
        while types[-1:] != ["response.completed"] and types[-1:] != ["response.failed"]:
            types.append(json.loads(ws.receive_text())["type"])

    assert rec["url"] == "http://oc:8000/v3/chat"
    assert types[-1] == "response.completed"


def test_malformed_frame_does_not_kill_the_connection():
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))), \
         TestClient(_client_app()) as client, \
         client.websocket_connect("/api/v1/responses") as ws:
        ws.send_text("not json")
        error = json.loads(ws.receive_text())
        assert error["type"] == "error"

        ws.send_text(json.dumps({
            "type": "response.create", "model": "onechat", "input": "บัตรหาย",
        }))
        types = []
        while types[-1:] != ["response.completed"]:
            types.append(json.loads(ws.receive_text())["type"])
    assert types[-1] == "response.completed"


def test_binary_frame_errors_without_closing():
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))), \
         TestClient(_client_app()) as client, \
         client.websocket_connect("/api/v1/responses") as ws:
        ws.send_bytes(b'{"type":"response.create","input":"x"}')
        error = json.loads(ws.receive_text())
        assert error["type"] == "error"

        ws.send_text(json.dumps({
            "type": "response.create", "model": "onechat", "input": "บัตรหาย",
        }))
        types = []
        while types[-1:] != ["response.completed"]:
            types.append(json.loads(ws.receive_text())["type"])
    assert types[-1] == "response.completed"


def test_connection_cap_refuses_the_next_connection(restore_cap):
    settings.RESPONSES_WS_MAX_CONNECTIONS = 1
    with TestClient(_client_app()) as client:
        with client.websocket_connect("/api/v1/responses") as first:
            with pytest.raises(Exception):
                with client.websocket_connect("/api/v1/responses"):
                    pass


def test_failed_accept_does_not_leak_the_connection_slot():
    async def _boom(self, *args, **kwargs):
        raise RuntimeError("handshake boom")

    starting = responses_router._connections._open
    with patch.object(WebSocket, "accept", _boom):
        with TestClient(_client_app()) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/api/v1/responses"):
                    pass
    assert responses_router._connections._open == starting
