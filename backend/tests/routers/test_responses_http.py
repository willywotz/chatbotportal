"""POST /api/v1/responses — the OpenAI-compatible HTTP surface."""

import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient
from tortoise import Tortoise

from app.errors import register_error_handlers
from app.models.conversation import Conversation, Message
from app.schemas.responses import ResponsesRequest
from app.routers import responses as responses_router
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent
from app.services.responses.errors import ResponsesApiError

ANSWER_DATA = {
    "answer": "คำตอบเต็ม", "summary": "สรุป",
    "references": [{"number": 1, "agency_id": "a-1", "agency_name": "กรม", "url": None}],
    "sections": [], "errors": [],
}


def _fake_live(*events: ChatEvent):
    """Replace _stream_live so no upstream HTTP call happens.

    Real _stream_live also persists the turn (Message + ConnectionLog) before
    its terminal `done` event, so the fake replays that side effect too —
    otherwise every assertion against saved rows would fail regardless of
    the router's implementation.
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


def _default_events(conversation_id: str):
    return (
        ChatEvent("step", {"name": "summarize"}),
        ChatEvent("answer", ANSWER_DATA),
        ChatEvent("done", {"session_id": conversation_id, "total_ms": 900}),
    )


def _body(response) -> dict:
    """Decode a non-streaming create_response() return (a JSONResponse)."""
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_non_streaming_returns_a_complete_response(db):
    request = ResponsesRequest(model="thai-citizen-guide-v5", input="บัตรหาย")
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        response = await responses_router.create_response(
            request, BackgroundTasks(), user=None,
        )

    body = _body(response)
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["output_text"] == "คำตอบเต็ม"
    assert body["model"] == "thai-citizen-guide-v5"
    assert body["portal"]["summary"] == "สรุป"
    assert body["id"].startswith("resp_")

    saved = await Message.get(id=uuid.UUID(body["id"].removeprefix("resp_")))
    assert saved.role == "assistant"
    assert saved.content == "คำตอบเต็ม"


@pytest.mark.asyncio
async def test_streaming_emits_the_openai_sequence(db):
    request = ResponsesRequest(model="thai-citizen-guide", input="บัตรหาย", stream=True)
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        response = await responses_router.create_response(
            request, BackgroundTasks(), user=None,
        )
        chunks = [c async for c in response.body_iterator]

    text = "".join(c if isinstance(c, str) else c.decode() for c in chunks)
    types = [json.loads(line[6:])["type"]
             for line in text.splitlines()
             if line.startswith("data: ") and line != "data: [DONE]"]
    assert types == [
        "response.created", "response.output_item.added", "response.content_part.added",
        "response.output_text.delta", "response.output_text.done",
        "response.content_part.done", "response.output_item.done", "response.completed",
    ]
    assert text.rstrip().endswith("data: [DONE]")


@pytest.mark.asyncio
async def test_previous_response_id_continues_the_conversation(db):
    first = ResponsesRequest(model="thai-citizen-guide", input="หนึ่ง")
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        body = _body(await responses_router.create_response(first, BackgroundTasks(), user=None))

    conversation_id = body["portal"]["conversation_id"]
    second = ResponsesRequest(
        model="thai-citizen-guide", input="สอง", previous_response_id=body["id"],
    )
    with patch.object(turn_stream, "ensure_session_warmed", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        second_response = await responses_router.create_response(second, BackgroundTasks(), user=None)
    second_body = _body(second_response)

    assert second_body["portal"]["conversation_id"] == conversation_id
    assert second_body["id"] != body["id"]
    assert await Message.filter(conversation_id=conversation_id).count() == 4


@pytest.mark.asyncio
async def test_unknown_model_raises_a_responses_error(db):
    with pytest.raises(ResponsesApiError) as exc:
        await responses_router.create_response(
            ResponsesRequest(model="gpt-5", input="hi"), BackgroundTasks(), user=None,
        )
    assert exc.value.status == 400
    assert exc.value.param == "model"


@pytest.mark.asyncio
async def test_unknown_previous_response_id_raises_404(db):
    request = ResponsesRequest(
        model="thai-citizen-guide", input="hi", previous_response_id=f"resp_{uuid.uuid4()}",
    )
    with pytest.raises(ResponsesApiError) as exc:
        await responses_router.create_response(request, BackgroundTasks(), user=None)
    assert exc.value.code == "previous_response_not_found"


@pytest.mark.asyncio
async def test_empty_input_raises_400(db):
    with pytest.raises(ResponsesApiError):
        await responses_router.create_response(
            ResponsesRequest(model="thai-citizen-guide", input="   "),
            BackgroundTasks(), user=None,
        )


@pytest.mark.asyncio
async def test_cache_hit_is_reported_in_portal(db):
    conv = await Conversation.create(status="success")
    user_msg = await Message.create(conversation=conv, role="user", content="q")
    asst_msg = await Message.create(
        parent_id=user_msg.id, conversation=conv, role="assistant", content="cached answer"
    )

    class _Log:
        response_body = json.dumps({"answer": "cached answer"})

    with patch.object(turn_stream, "find_similar_question",
                      new=AsyncMock(return_value=(user_msg, asst_msg, _Log()))):
        response = await responses_router.create_response(
            ResponsesRequest(model="thai-citizen-guide", input="q"),
            BackgroundTasks(), user=None,
        )

    body = _body(response)
    assert body["portal"]["cached"] is True
    assert body["output_text"] == "cached answer"


@pytest.mark.asyncio
async def test_one_connection_log_per_turn(db):
    from app.models.connection_log import ConnectionLog

    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        await responses_router.create_response(
            ResponsesRequest(model="thai-citizen-guide", input="hi"),
            BackgroundTasks(), user=None,
        )
    assert await ConnectionLog.filter(action="query").count() == 1


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


def _client_app() -> FastAPI:
    """A real ASGI app mounting the responses router.

    Calling `create_response()` as a bare coroutine (as the tests above do)
    never constructs a `StreamingResponse`, so it cannot catch bugs that only
    manifest once `StreamingResponse` has committed HTTP headers before the
    generator's first `__anext__()`. `TestClient` drives the real ASGI stack,
    so it can.
    """
    app = FastAPI(lifespan=_lifespan)
    register_error_handlers(app)
    app.include_router(responses_router.router, prefix="/api/v1")
    return app


def test_streaming_unknown_model_returns_400_over_http():
    with TestClient(_client_app()) as client:
        r = client.post(
            "/api/v1/responses", json={"model": "gpt-5", "input": "hi", "stream": True},
        )
    assert r.status_code == 400
    assert r.json()["error"]["param"] == "model"


def test_streaming_unknown_previous_response_id_returns_404_over_http():
    with TestClient(_client_app()) as client:
        r = client.post(
            "/api/v1/responses",
            json={
                "model": "thai-citizen-guide", "input": "hi", "stream": True,
                "previous_response_id": f"resp_{uuid.uuid4()}",
            },
        )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "previous_response_not_found"


@pytest.mark.asyncio
async def test_upstream_error_becomes_response_failed(db):
    request = ResponsesRequest(model="thai-citizen-guide", input="hi", stream=True)
    events = (
        ChatEvent("error", {"message": "OneChat v5 returned 502", "code": 502}),
        ChatEvent("done", {"session_id": "s", "total_ms": 0}),
    )
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*events)):
        response = await responses_router.create_response(request, BackgroundTasks(), user=None)
        chunks = [c async for c in response.body_iterator]

    text = "".join(c if isinstance(c, str) else c.decode() for c in chunks)
    types = [json.loads(line[6:])["type"]
             for line in text.splitlines()
             if line.startswith("data: ") and line != "data: [DONE]"]
    assert types == ["response.created", "response.failed"]
