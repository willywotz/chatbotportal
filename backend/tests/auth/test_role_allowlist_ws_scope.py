"""enforce_role_allowlist must not blow up on WebSocket scopes.

Regression for a production 500: the global dependency (wired in app.main via
FastAPI(dependencies=[...])) runs on every route including WebSockets, but
FastAPI cannot inject a Request for a WS handshake. See app/auth/dependencies.py.
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket

from app.auth.dependencies import enforce_role_allowlist


@pytest.mark.asyncio
async def test_websocket_scope_returns_none_without_raising():
    ws = WebSocket(
        {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""},
        receive=None,
        send=None,
    )
    assert await enforce_role_allowlist(ws) is None


def test_global_dependency_does_not_break_websocket_handshake():
    """The app-level regression: without the fix this 500s with a TypeError
    before the handler runs (missing 'request' arg for a WS connection)."""
    app = FastAPI(dependencies=[Depends(enforce_role_allowlist)])

    @app.websocket("/ws")
    async def echo(websocket: WebSocket) -> None:
        await websocket.accept()
        msg = await websocket.receive_text()
        await websocket.send_text(msg)
        await websocket.close()

    with TestClient(app).websocket_connect("/ws") as client:
        client.send_text("ping")
        assert client.receive_text() == "ping"
