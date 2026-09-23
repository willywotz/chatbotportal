"""Smuggle W3C trace context through URLs OneChat preserves.

OneChat drops the traceparent header between hops but keeps URL query strings,
so we carry the context in a ?traceparent= query param and extract it on the
receiving side (header still wins when present).
"""
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from opentelemetry.propagate import inject


def trace_context_params() -> dict:
    carrier: dict = {}
    inject(carrier)
    return {k: carrier[k] for k in ("traceparent", "tracestate") if k in carrier}


def with_trace_query(url: str) -> str:
    """Append the current W3C context to url's query. No-op if no active context."""
    params = trace_context_params()
    if not params:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.update(params)
    return urlunsplit(parts._replace(query=urlencode(query)))


class QueryTraceparentASGI:
    """ASGI shim: promote ?traceparent/&tracestate query params to request
    headers when the header is absent, so downstream header-based OTel
    extraction continues the trace."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            qs = parse_qs(scope.get("query_string", b"").decode())
            existing = {k for k, _ in scope["headers"]}
            headers = list(scope["headers"])
            for name in ("traceparent", "tracestate"):
                val = qs.get(name, [None])[0]
                if val and name.encode() not in existing:
                    headers.append((name.encode(), val.encode()))
            scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)
