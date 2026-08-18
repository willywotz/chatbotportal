"""OneChat drops the traceparent header but preserves URL query strings, so
_stream_live must smuggle the active trace context into the MCP endpoint URL
it hands to the OneChat client."""

from unittest.mock import AsyncMock

from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.main as main  # ensures tracer provider is configured
import app.services.chat.stream as stream_mod
from app.services.chat.stream import TurnPlan, _stream_live
from app.utils import generate_uuid


def _make_plan(conversation_id: str) -> TurnPlan:
    return TurnPlan(
        query="q", conversation_id=conversation_id, user=None, stream_version="v5",
        assistant_message_id=generate_uuid(),
    )


async def test_stream_live_passes_traceparent_tagged_mcp_url(monkeypatch):
    exporter = InMemorySpanExporter()
    main.tracerProvider.add_span_processor(SimpleSpanProcessor(exporter))

    recorded = {}

    async def fake_events(query, mcp_url, session_id):
        recorded["mcp_url"] = mcp_url
        yield ("answer", {"answer": "hi"})
        yield ("done", {"session_id": session_id, "total_ms": 1})

    class _Stub:
        def events(self, *a, **k):
            return fake_events(*a, **k)

    monkeypatch.setattr(stream_mod, "get_client", lambda v: _Stub())
    monkeypatch.setattr(stream_mod, "_persist", AsyncMock(return_value=generate_uuid()))

    with trace.get_tracer(__name__).start_as_current_span("outer"):
        plan = _make_plan(conversation_id="conv-xyz")
        _ = [ev async for ev in _stream_live(plan, schedule=None)]

    assert "traceparent=" in recorded["mcp_url"]
