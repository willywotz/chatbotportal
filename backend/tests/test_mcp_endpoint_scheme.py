"""The agent-proxy endpoint_url must carry the *external* client scheme.

Behind a Cloudflare tunnel the whole chain (cloudflared -> nginx -> backend)
speaks plain HTTP, so request.url.scheme and X-Forwarded-Proto are both "http".
The only header that preserves the browser's real scheme is `cf-visitor`
(`{"scheme":"https"}`). Building endpoint_url from request.url.scheme therefore
hands clients an http:// URL that a https origin refuses. _external_scheme must
prefer cf-visitor, then X-Forwarded-Proto, then the raw connection scheme.
"""

from starlette.datastructures import Headers
from starlette.requests import Request

from app.mcp.server import _external_scheme


def _request(headers: dict) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request(
        {"type": "http", "scheme": "http", "path": "/", "server": ("testserver", 80), "headers": raw}
    )


def test_cf_visitor_scheme_wins_over_http_connection():
    request = _request({"cf-visitor": '{"scheme":"https"}', "x-forwarded-proto": "http"})
    assert _external_scheme(request) == "https"


def test_falls_back_to_forwarded_proto_without_cf_visitor():
    request = _request({"x-forwarded-proto": "https"})
    assert _external_scheme(request) == "https"


def test_falls_back_to_connection_scheme_when_no_headers():
    request = _request({})
    assert _external_scheme(request) == "http"


def test_malformed_cf_visitor_falls_through():
    request = _request({"cf-visitor": "not-json", "x-forwarded-proto": "https"})
    assert _external_scheme(request) == "https"
