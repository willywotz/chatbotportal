import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from opentelemetry import trace

import app.main  # noqa: F401 — configures the SDK tracer provider and instruments httpx (the change under test)
from app.services.onechat import OneChatClient


class _CaptureHandler(BaseHTTPRequestHandler):
    captured: dict = {}

    def do_POST(self):
        _CaptureHandler.captured["traceparent"] = self.headers.get("traceparent")
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        payload = b'{"data": {"answer": "x"}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def _server():
    _CaptureHandler.captured = {}
    srv = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


async def test_onechat_request_carries_traceparent(_server):
    port = _server.server_address[1]
    client = OneChatClient(f"http://127.0.0.1:{port}", version="v3")
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("root") as span:
        expected = format(span.get_span_context().trace_id, "032x")
        _ = [ev async for ev in client.events("q", "http://mcp", "c")]

    tp = _CaptureHandler.captured.get("traceparent")
    assert tp is not None, "no traceparent injected on OneChat call"
    assert expected in tp, "traceparent trace id does not match active span"
