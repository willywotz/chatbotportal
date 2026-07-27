from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

import app.main as main
from app.trace_util import QueryTraceparentASGI


def _mcp_mount(fastapi_app):
    for route in fastapi_app.routes:
        if getattr(route, "path", None) == "/mcp":
            return route
    raise AssertionError("/mcp mount not found")


def test_mcp_mount_is_otel_wrapped():
    mount = _mcp_mount(main.app)
    assert isinstance(mount.app, QueryTraceparentASGI), (
        "/mcp sub-app must be wrapped in QueryTraceparentASGI first, so an incoming "
        "?traceparent= query param (OneChat drops the header but keeps the query "
        "string) is promoted to a header before OpenTelemetryMiddleware extracts it."
    )
    assert isinstance(mount.app.app, OpenTelemetryMiddleware), (
        "QueryTraceparentASGI must wrap OpenTelemetryMiddleware, so the promoted "
        "traceparent header continues the trace on the OneChat->MCP callback."
    )
