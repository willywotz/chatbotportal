"""End-to-end guard: repeated list_agency calls over /mcp never hit a session error.

The original report was an intermittent "Session terminated" — a stateful MCP
session pinned to one worker that a later request failed to find. The /mcp app
is now stateless (mcp.http_app(stateless_http=True)), so every request is
self-contained and any worker can serve any call.

This stands up the real mcp_app on a loopback Streamable-HTTP server and calls
the real list_agency tool many times — both repeatedly within one client
session and across several fresh sessions. A regression to stateful mode (or a
broken session lifecycle) surfaces here as an McpError instead of a clean
result.

Both call patterns live in one test because StreamableHTTPSessionManager.run()
(entered via mcp_app.lifespan) may only run once per app instance, and we want
to exercise the real, configured mcp_app rather than a throwaway copy.
"""

import asyncio
import contextlib
import socket

import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from starlette.applications import Starlette
from starlette.routing import Mount
from tortoise import Tortoise

import app.main as main
from app.models.agency import Agency

_CALLS = 5
_SESSIONS = 3


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@contextlib.asynccontextmanager
async def _mcp_lifespan(_app):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    await Agency.create(
        name="DOPA", description="d", connection_type="API", data_scope=["x"],
        endpoint_url="http://e/dopa/chat",
        expected_payload={"query": "", "session_id": ""}, status="active",
    )
    async with main.mcp_app.lifespan(_app):
        yield
    await Tortoise.close_connections()


def _transport(url: str) -> StreamableHttpTransport:
    return StreamableHttpTransport(url, headers={"X-Forwarded-Host": "example.test"})


@pytest.mark.asyncio
async def test_repeated_list_agency_calls_have_no_session_error():
    root = Starlette(routes=[Mount("/mcp", app=main.mcp_app)], lifespan=_mcp_lifespan)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(root, host="127.0.0.1", port=port, log_level="warning", lifespan="on", ws="none")
    )
    serve_task = asyncio.create_task(server.serve())
    url = f"http://127.0.0.1:{port}/mcp/"
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started, "loopback MCP server did not start"

        async with asyncio.timeout(30):
            async with Client(_transport(url)) as client:
                for _ in range(_CALLS):
                    result = await client.call_tool("list_agency", {})
                    assert (result.structured_content or {}).get("total") == 1

            # A fresh session (its own initialize) per call — the stateless path.
            for _ in range(_SESSIONS):
                async with Client(_transport(url)) as client:
                    result = await client.call_tool("list_agency", {})
                    assert (result.structured_content or {}).get("total") == 1
    finally:
        server.should_exit = True
        await serve_task
