"""Merged POST /chat: JSON by default, SSE when stream=true, model picks version."""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks

from app.routers import chat as chat_router
from app.schemas.chat import ChatRequest
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent


def _events():
    return [
        ChatEvent("step", {"name": "discover", "status": "done"}),
        ChatEvent("answer", {"answer": "คำตอบ", "summary": "S", "sections": [],
                             "references": [], "errors": []}),
        ChatEvent("done", {"session_id": "c1", "total_ms": 42, "message_id": "m-1"}),
    ]


def _fake_run_turn(*events):
    async def gen(plan, *, background_tasks=None):
        for e in events:
            yield e
    return gen


@pytest.mark.asyncio
async def test_json_response_default(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(chat_router, "run_turn", _fake_run_turn(*_events())), \
         patch("app.services.chat.aggregate.run_turn", _fake_run_turn(*_events())):
        result = await chat_router.chat(ChatRequest(query="q"), BackgroundTasks(), None)
    assert result["success"] is True
    assert result["data"]["answer"] == "คำตอบ"
    assert result["data"]["summary"] == "S"
    assert result["data"]["message_id"] == "m-1"
    assert result["data"]["cached"] is False
    assert result["responseTime"] == 42


@pytest.mark.asyncio
async def test_sse_response_when_stream_true(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(chat_router, "run_turn", _fake_run_turn(*_events())):
        resp = await chat_router.chat(ChatRequest(query="q", stream=True), BackgroundTasks(), None)
        chunks = [c async for c in resp.body_iterator]
    text = "".join(c if isinstance(c, str) else c.decode() for c in chunks)
    assert resp.media_type == "text/event-stream"
    assert "event: answer" in text
    assert "event: done" in text


@pytest.mark.asyncio
async def test_empty_query_is_400(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await chat_router.chat(ChatRequest(query="   "), BackgroundTasks(), None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_model_selects_version_v3(db):
    captured = {}

    async def fake_prepare(*, query, conversation_id, user, is_continuation, requested_version=None):
        captured["version"] = requested_version
        from app.services.chat.stream import TurnPlan
        from app.utils import generate_uuid
        return TurnPlan(query=query, conversation_id=conversation_id, user=user,
                        stream_version=requested_version, assistant_message_id=generate_uuid())

    with patch.object(chat_router, "prepare_turn", fake_prepare), \
         patch.object(chat_router, "run_turn", _fake_run_turn(*_events())), \
         patch("app.services.chat.aggregate.run_turn", _fake_run_turn(*_events())):
        await chat_router.chat(ChatRequest(query="q", model="onechat-v3"), BackgroundTasks(), None)
    assert captured["version"] == "v3"
