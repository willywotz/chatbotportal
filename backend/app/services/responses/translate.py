"""Translate portal ChatEvents into OpenAI Responses events.

Pure and transport-free: SSE, WebSocket and the non-streaming path all drive the
same accumulator, so they cannot drift.

OneChat delivers the answer as one terminal `answer` event, not token deltas, so
the stream is a correct OpenAI sequence containing a single large delta. If the
upstream ever emits incremental text, `consume()` naturally emits several
`response.output_text.delta` events with no change to any caller.
"""
import time
from typing import Any

from app.services.chat.stream import ChatEvent

_ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

# Upstream pipeline-progress events have no standard Responses counterpart.
# Injecting non-standard event types is what breaks strict SDK parsers, so they
# are dropped; clients wanting the pipeline view use /chat/stream.
_IGNORED = frozenset(
    {"step", "intent", "routing", "agency_start", "agency_responded", "agency_verified"}
)


class ResponseAccumulator:
    def __init__(
        self, response_id: str, model: str, conversation_id: str,
        *, cached: bool = False, stream_version: str = "v5",
    ):
        self.response_id = response_id
        self.item_id = "msg_" + response_id.removeprefix("resp_")
        self.model = model
        self.conversation_id = conversation_id
        self.cached = cached
        self.stream_version = stream_version
        self.created_at = int(time.time())
        self.answer = ""
        self.summary = ""
        self.references: list[dict] = []
        self.agency_ids: list[str] = []
        self.failed = False
        self.error: dict | None = None
        self._sequence = 0

    def _next(self) -> int:
        value = self._sequence
        self._sequence += 1
        return value

    def created_event(self) -> dict:
        return {
            "type": "response.created",
            "sequence_number": self._next(),
            "response": self._response_body(status="in_progress", with_output=False),
        }

    def consume(self, event: ChatEvent) -> list[dict]:
        if event.name in _IGNORED:
            return []
        if event.name == "error":
            return [self._failed(event.data.get("message", "Upstream error"))]
        if event.name == "answer":
            return self._answer_events(event.data)
        if event.name == "done":
            if self.failed:
                return []
            return [{
                "type": "response.completed",
                "sequence_number": self._next(),
                "response": self.final_response(),
            }]
        return []

    def _answer_events(self, data: dict) -> list[dict]:
        self.answer = (data.get("answer") or "").strip()
        self.summary = (data.get("summary") or "").strip()
        self.references = data.get("references") or []
        self.agency_ids = [
            agency["id"]
            for section in data.get("sections") or []
            for agency in section.get("agencies", [])
        ]
        part = {"type": "output_text", "text": self.answer, "annotations": []}
        return [
            {
                "type": "response.output_item.added",
                "sequence_number": self._next(),
                "output_index": 0,
                "item": {
                    "id": self.item_id, "type": "message", "status": "in_progress",
                    "role": "assistant", "content": [],
                },
            },
            {
                "type": "response.content_part.added",
                "sequence_number": self._next(),
                "item_id": self.item_id, "output_index": 0, "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            },
            {
                "type": "response.output_text.delta",
                "sequence_number": self._next(),
                "item_id": self.item_id, "output_index": 0, "content_index": 0,
                "delta": self.answer,
            },
            {
                "type": "response.output_text.done",
                "sequence_number": self._next(),
                "item_id": self.item_id, "output_index": 0, "content_index": 0,
                "text": self.answer,
            },
            {
                "type": "response.content_part.done",
                "sequence_number": self._next(),
                "item_id": self.item_id, "output_index": 0, "content_index": 0,
                "part": part,
            },
            {
                "type": "response.output_item.done",
                "sequence_number": self._next(),
                "output_index": 0,
                "item": {
                    "id": self.item_id, "type": "message", "status": "completed",
                    "role": "assistant", "content": [part],
                },
            },
        ]

    def _failed(self, message: str) -> dict:
        self.failed = True
        self.error = {"code": "server_error", "message": message}
        return {
            "type": "response.failed",
            "sequence_number": self._next(),
            "response": self._response_body(status="failed", with_output=False),
        }

    def final_response(self) -> dict:
        return self._response_body(status="completed", with_output=True)

    def _response_body(self, *, status: str, with_output: bool) -> dict:
        body: dict[str, Any] = {
            "id": self.response_id,
            "object": "response",
            "created_at": self.created_at,
            "status": status,
            "model": self.model,
            "output": [],
            "output_text": self.answer if with_output else "",
            # Always zero: OneChat does not report token counts to the portal and
            # inventing them would corrupt client-side cost accounting.
            "usage": dict(_ZERO_USAGE),
            "portal": {
                "conversation_id": self.conversation_id,
                "summary": self.summary,
                "references": self.references,
                "agency_ids": self.agency_ids,
                "cached": self.cached,
                "stream_version": self.stream_version,
            },
        }
        if with_output and self.answer:
            body["output"] = [{
                "id": self.item_id, "type": "message", "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": self.answer, "annotations": []}],
            }]
        if self.error is not None:
            body["error"] = self.error
        return body
