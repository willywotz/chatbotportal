"""OneChat drops the traceparent header but preserves URL query strings, so
trace context is smuggled through ?traceparent=/&tracestate= instead."""

from urllib.parse import parse_qs, urlsplit

from opentelemetry import trace

import app.main as main  # ensures the SDK tracer provider is configured
from app.trace_util import QueryTraceparentASGI, with_trace_query

tracer = trace.get_tracer(__name__)


def test_with_trace_query_adds_traceparent_inside_active_span():
    with tracer.start_as_current_span("t"):
        url = with_trace_query("https://example.com/mcp")

    query = parse_qs(urlsplit(url).query)
    assert "traceparent" in query


def test_with_trace_query_preserves_existing_query_params():
    with tracer.start_as_current_span("t"):
        url = with_trace_query("https://example.com/mcp?agency_id=abc")

    query = parse_qs(urlsplit(url).query)
    assert query["agency_id"] == ["abc"]
    assert "traceparent" in query


def test_with_trace_query_is_noop_without_active_span():
    url = with_trace_query("https://example.com/mcp")

    assert url == "https://example.com/mcp"


async def test_asgi_shim_promotes_query_traceparent_to_header():
    traceparent = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    scope = {
        "type": "http",
        "query_string": f"traceparent={traceparent}".encode(),
        "headers": [],
    }
    seen = {}

    async def inner_app(inner_scope, receive, send):
        seen["scope"] = inner_scope

    await QueryTraceparentASGI(inner_app)(scope, None, None)

    assert (b"traceparent", traceparent.encode()) in seen["scope"]["headers"]


async def test_asgi_shim_does_not_override_existing_header():
    traceparent = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    real_header = "00-" + "c" * 32 + "-" + "d" * 16 + "-01"
    scope = {
        "type": "http",
        "query_string": f"traceparent={traceparent}".encode(),
        "headers": [(b"traceparent", real_header.encode())],
    }
    seen = {}

    async def inner_app(inner_scope, receive, send):
        seen["scope"] = inner_scope

    await QueryTraceparentASGI(inner_app)(scope, None, None)

    values = [v for k, v in seen["scope"]["headers"] if k == b"traceparent"]
    assert values == [real_header.encode()]
