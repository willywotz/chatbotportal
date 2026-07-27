from unittest.mock import patch

import pytest

from app.services.chat import aggregate as agg
from app.services.chat.aggregate import collect_turn
from app.services.chat.stream import ChatEvent, TurnPlan
from app.utils import generate_uuid


def _plan() -> TurnPlan:
    return TurnPlan(query="q", conversation_id="c1", user=None,
                    stream_version="v5", assistant_message_id=generate_uuid())


def _fake_run_turn(*events):
    async def gen(plan, *, background_tasks=None):
        for e in events:
            yield e
    return gen


@pytest.mark.asyncio
async def test_collect_turn_folds_answer_steps_and_done():
    events = [
        ChatEvent("step", {"name": "discover", "status": "done"}),
        ChatEvent("answer", {"answer": "A", "summary": "S", "sections": [], "errors": []}),
        ChatEvent("done", {"session_id": "c1", "total_ms": 1234, "message_id": "msg-1"}),
    ]
    with patch.object(agg, "run_turn", _fake_run_turn(*events)):
        result = await collect_turn(_plan(), background_tasks=None)
    assert result.answer_data["answer"] == "A"
    assert result.answer_data["summary"] == "S"
    assert result.message_id == "msg-1"
    assert result.total_ms == 1234
    assert result.error is None
    assert result.cached is False


@pytest.mark.asyncio
async def test_collect_turn_captures_error_event():
    events = [
        ChatEvent("error", {"message": "boom", "code": 502}),
        ChatEvent("done", {"session_id": "c1", "total_ms": 0}),
    ]
    with patch.object(agg, "run_turn", _fake_run_turn(*events)):
        result = await collect_turn(_plan(), background_tasks=None)
    assert result.error == {"message": "boom", "code": 502}
