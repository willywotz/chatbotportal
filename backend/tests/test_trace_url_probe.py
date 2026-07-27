"""TRACE_URL_PROBE lets us append a marker query string to the endpoint_url
handed to OneChat, so Jaeger's proxy.incoming_query attribute (agent-proxy)
reveals whether OneChat preserves query strings on its callback.
"""

from starlette.requests import Request

from app.mcp.server import _agent_proxy_endpoint


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
