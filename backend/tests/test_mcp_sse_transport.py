"""Regression guard: the MCP SSE transport is NOT exposed.

The legacy OneChat-spec SSE transport (GET /sse + POST /messages/) was removed.
It drove the raw MCP SDK server over SseServerTransport, which is inherently
session-affine: the open stream lives in one process, so it cannot survive the
production `uvicorn --workers 4` deployment and cannot be made stateless like
the /mcp Streamable-HTTP app. Clients use /mcp instead.

This test fails if anyone re-adds the SSE routes, prompting a deliberate
decision rather than silently reintroducing a worker-fragile surface.
"""

import app.main as main


def _route_paths(starlette_app) -> set[str]:
    return {getattr(route, "path", None) for route in starlette_app.routes}


def test_sse_route_is_not_exposed():
    assert "/sse" not in _route_paths(main.app)


def test_messages_mount_is_not_exposed():
    """The root-level /messages mount (MCP SSE POST channel) must not exist.

    The REST message router lives under /api/v1/messages, so a bare /messages
    mount can only be the removed SSE transport.
    """
    assert "/messages" not in _route_paths(main.app)


def test_sse_transport_symbols_removed():
    assert not hasattr(main, "_sse_handler")
    assert not hasattr(main, "_sse_transport")
