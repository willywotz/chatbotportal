"""The OneChat call must carry a conversation_id-tagged span so fragments can
be joined in Jaeger even when OneChat does not forward traceparent."""

from unittest.mock import AsyncMock

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


async def test_onechat_span_tags_conversation_id(monkeypatch):
    exporter = InMemorySpanExporter()
    main.tracerProvider.add_span_processor(SimpleSpanProcessor(exporter))

    async def fake_events(query, mcp_url, session_id):
        yield ("answer", {"answer": "hi"})
        yield ("done", {"session_id": session_id, "total_ms": 1})

    class _Stub:
        def events(self, *a, **k):
            return fake_events(*a, **k)

    monkeypatch.setattr(stream_mod, "get_client", lambda v: _Stub())
    monkeypatch.setattr(stream_mod, "_persist", AsyncMock(return_value=generate_uuid()))

    plan = _make_plan(conversation_id="conv-xyz")
    _ = [ev async for ev in _stream_live(plan, background_tasks=None)]

    spans = exporter.get_finished_spans()
    tagged = [s for s in spans if s.attributes.get("conversation_id") == "conv-xyz"]
    assert any(s.name == "onechat_call" for s in tagged), "onechat_call span missing conversation_id tag"
