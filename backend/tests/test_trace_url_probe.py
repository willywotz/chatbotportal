"""TRACE_URL_PROBE lets us append a marker query string to the endpoint_url
handed to OneChat, so Jaeger's proxy.incoming_query attribute (agent-proxy)
reveals whether OneChat preserves query strings on its callback.
"""

from urllib.parse import parse_qs, urlsplit

from opentelemetry import trace
from starlette.requests import Request

import app.main as main  # ensures the SDK tracer provider is configured
from app.mcp.server import _agent_proxy_endpoint

tracer = trace.get_tracer(__name__)


def _request(headers: dict) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request(
        {"type": "http", "scheme": "http", "path": "/", "server": ("testserver", 80), "headers": raw}
    )


def test_no_query_when_probe_disabled(monkeypatch):
    import app.mcp.server as server

    monkeypatch.setattr(server.settings, "TRACE_URL_PROBE", "")
    request = _request({"x-forwarded-host": "example.com", "x-forwarded-proto": "https"})

    url = _agent_proxy_endpoint(request, "11111111-1111-4111-8111-111111111111")

    assert "?" not in url


def test_appends_probe_query_when_enabled(monkeypatch):
    import app.mcp.server as server

    monkeypatch.setattr(server.settings, "TRACE_URL_PROBE", "tp_probe=AP1")
    request = _request({"x-forwarded-host": "example.com", "x-forwarded-proto": "https"})

    url = _agent_proxy_endpoint(request, "11111111-1111-4111-8111-111111111111")

    assert url.endswith("?tp_probe=AP1")


def test_carries_traceparent_when_span_active(monkeypatch):
    import app.mcp.server as server

    monkeypatch.setattr(server.settings, "TRACE_URL_PROBE", "")
    request = _request({"x-forwarded-host": "example.com", "x-forwarded-proto": "https"})

    with tracer.start_as_current_span("t"):
        url = _agent_proxy_endpoint(request, "11111111-1111-4111-8111-111111111111")

    assert "traceparent" in parse_qs(urlsplit(url).query)


def test_no_traceparent_when_span_inactive():
    request = _request({"x-forwarded-host": "example.com", "x-forwarded-proto": "https"})

    url = _agent_proxy_endpoint(request, "11111111-1111-4111-8111-111111111111")

    assert "?" not in url


def test_endpoint_uses_api_v1_agent_proxy_path():
    request = _request({"x-forwarded-host": "example.com", "x-forwarded-proto": "https"})
    url = _agent_proxy_endpoint(request, "11111111-1111-4111-8111-111111111111")
    assert "/api/v1/agent-proxy/11111111-1111-4111-8111-111111111111" in url
