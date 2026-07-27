from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

import app.main as main


def _mcp_mount(fastapi_app):
    for route in fastapi_app.routes:
        if getattr(route, "path", None) == "/mcp":
            return route
    raise AssertionError("/mcp mount not found")


def test_mcp_mount_is_otel_wrapped():
    mount = _mcp_mount(main.app)
    assert isinstance(mount.app, OpenTelemetryMiddleware), (
        "/mcp sub-app must be wrapped in OpenTelemetryMiddleware so an incoming "
        "traceparent on the OneChat->MCP callback continues the trace. Mounted "
        "sub-apps are never covered by FastAPIInstrumentor.instrument_app."
    )
