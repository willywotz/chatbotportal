"""Regression guard: the /mcp Streamable-HTTP app must be stateless.

Production runs uvicorn with `--workers 4` (see backend/Dockerfile). Stateful
MCP sessions store the session object in the worker process that handled the
`initialize` request. With no session affinity across workers, a follow-up
request carrying the `Mcp-Session-Id` can land on a different worker that has
never seen that session, which makes the MCP client raise an intermittent
"Session terminated" error.

Stateless mode (a fresh transport per request) removes the cross-worker
session dependency, so any worker can serve any request. FastMCP signals this
by dropping the GET SSE stream from the Streamable-HTTP route: stateless routes
accept only POST/DELETE, never GET.
"""

import app.main as main


def _streamable_route(starlette_app):
    for route in starlette_app.routes:
        if getattr(route, "path", None) == "/":
            return route
    raise AssertionError("Streamable-HTTP route '/' not found on mcp_app")


def test_mcp_app_is_stateless():
    route = _streamable_route(main.mcp_app)
    assert route.methods is not None, (
        "Streamable-HTTP route allows all methods (GET included) — the app is "
        "stateful. Build it with mcp.http_app(path='/', stateless_http=True) so "
        "it survives multiple uvicorn workers without session affinity."
    )
    assert "GET" not in route.methods, (
        f"Streamable-HTTP route still serves GET ({sorted(route.methods)}); a "
        "stateless app exposes only POST/DELETE."
    )
