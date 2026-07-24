"""WebSocket frame handling, tested without a socket."""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent
from app.services.responses import session as ws_session
from app.services.responses.session import WsSession

ANSWER_DATA = {"answer": "คำตอบ", "summary": "", "references": [], "sections": [], "errors": []}


def _fake_live(*events: ChatEvent):
    """Replace _stream_live so no upstream HTTP call happens.

    Real _stream_live also persists the turn (Message + ConnectionLog) before
    its terminal `done` event, so the fake replays that side effect too —
    otherwise a continuation naming this turn's conversation would find no
    row. Mirrors tests/routers/test_responses_http.py's `_fake_live`.
    """
    async def _run(plan, background_tasks):
        answer_data = None
        for event in events:
            if event.name == "answer":
                answer_data = event.data
            yield event
        if answer_data is not None:
            await turn_stream._persist(
                plan, answer_data=answer_data, session_id=None, total_ms=0,
                latency_ms=0, thread_name=None, background_tasks=background_tasks,
            )
    return _run


def _default_events():
    return (
        ChatEvent("answer", ANSWER_DATA),
        ChatEvent("done", {"session_id": "s", "total_ms": 10}),
    )


class _Sink:
    def __init__(self):
        self.frames: list[dict] = []

    async def __call__(self, frame: dict) -> None:
        self.frames.append(frame)

    @property
    def types(self) -> list[str]:
        return [f["type"] for f in self.frames]


def _create(**overrides) -> str:
    payload = {"type": "response.create", "model": "thai-citizen-guide", "input": "q"}
    payload.update(overrides)
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_response_create_emits_the_full_sequence(db):
    sink = _Sink()
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
        await WsSession(user=None).handle_text(_create(), sink)

    assert sink.types == [
        "response.created", "response.output_item.added", "response.content_part.added",
        "response.output_text.delta", "response.output_text.done",
        "response.content_part.done", "response.output_item.done", "response.completed",
    ]


@pytest.mark.asyncio
async def test_two_sequential_creates_both_complete(db):
    sink = _Sink()
    session = WsSession(user=None)
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
        await session.handle_text(_create(), sink)
        await session.handle_text(_create(input="another"), sink)

    assert sink.types.count("response.completed") == 2


@pytest.mark.asyncio
async def test_the_connection_cache_serves_a_continuation(db):
    sink = _Sink()
    session = WsSession(user=None)
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
        await session.handle_text(_create(), sink)

    first_id = sink.frames[-1]["response"]["id"]
    conversation_id = sink.frames[-1]["response"]["portal"]["conversation_id"]
    assert session.cache[first_id] == conversation_id

    with patch.object(turn_stream, "ensure_session_warmed", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
        await session.handle_text(_create(previous_response_id=first_id), sink)

    assert sink.frames[-1]["response"]["portal"]["conversation_id"] == conversation_id


@pytest.mark.asyncio
async def test_generate_false_warms_without_generating(db):
    from app.models.conversation import Conversation, Message

    conv = await Conversation.create(status="success")
    await Message.create(conversation=conv, role="user", content="q")
    sink = _Sink()
    warm = AsyncMock(return_value=None)

    # `_warm` calls the name bound in session.py, not the one in stream.py.
    with patch.object(ws_session, "ensure_session_warmed", new=warm):
        await WsSession(user=None).handle_text(
            _create(generate=False, conversation=str(conv.id)), sink
        )

    assert warm.await_count == 1
    assert sink.types == []
    assert await Message.filter(conversation_id=conv.id).count() == 1


@pytest.mark.asyncio
async def test_unknown_previous_response_id_errors_without_closing(db):
    sink = _Sink()
    await WsSession(user=None).handle_text(
        _create(previous_response_id=f"resp_{uuid.uuid4()}"), sink
    )
    assert sink.types == ["error"]
    assert sink.frames[0]["error"]["code"] == "previous_response_not_found"


@pytest.mark.asyncio
async def test_malformed_json_errors_without_closing(db):
    sink = _Sink()
    await WsSession(user=None).handle_text("{not json", sink)
    assert sink.types == ["error"]
    assert sink.frames[0]["error"]["type"] == "invalid_request_error"


@pytest.mark.asyncio
async def test_unknown_frame_type_is_rejected(db):
    sink = _Sink()
    await WsSession(user=None).handle_text(json.dumps({"type": "session.update"}), sink)
    assert sink.types == ["error"]
    assert "response.create" in sink.frames[0]["error"]["message"]


@pytest.mark.asyncio
async def test_null_input_errors_without_closing(db):
    sink = _Sink()
    await WsSession(user=None).handle_text(_create(input=None), sink)
    assert sink.types == ["error"]
    assert sink.frames[0]["error"]["type"] == "invalid_request_error"


@pytest.mark.asyncio
async def test_wrong_type_model_errors_without_closing(db):
    sink = _Sink()
    await WsSession(user=None).handle_text(_create(model=123), sink)
    assert sink.types == ["error"]
    assert sink.frames[0]["error"]["type"] == "invalid_request_error"


@pytest.mark.asyncio
async def test_upstream_runtime_error_errors_without_closing(db):
    sink = _Sink()

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("upstream exploded")
        yield  # pragma: no cover - makes this an async generator

    from app.routers import responses as responses_router

    with patch.object(responses_router, "run_response", new=_boom):
        await WsSession(user=None).handle_text(_create(), sink)

    assert sink.types == ["error"]
    assert sink.frames[0]["error"]["type"] == "server_error"


@pytest.mark.asyncio
async def test_deeply_nested_json_errors_without_closing(db):
    sink = _Sink()
    nested = "[" * 20000 + "]" * 20000
    await WsSession(user=None).handle_text(nested, sink)
    assert sink.types == ["error"]
    assert sink.frames[0]["error"]["type"] == "invalid_request_error"


def test_ws_settings_are_registered():
    assert settings.RESPONSES_WS_MAX_CONNECTIONS == 1024
    assert settings.RESPONSES_WS_MAX_DURATION_SECONDS == 900
