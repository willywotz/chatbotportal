"""The /responses surface speaks OpenAI's error envelope, not the portal's."""

import pytest

from app.services.responses.errors import ResponsesApiError


def test_envelope_matches_openai_shape():
    err = ResponsesApiError("Unknown model 'gpt-5'.", param="model")
    assert err.status == 400
    assert err.envelope() == {
        "error": {
            "message": "Unknown model 'gpt-5'.",
            "type": "invalid_request_error",
            "param": "model",
            "code": None,
        }
    }


def test_not_found_carries_its_code_and_status():
    err = ResponsesApiError(
        "Previous response with id 'resp_abc' not found",
        code="previous_response_not_found", status=404,
    )
    assert err.status == 404
    assert err.envelope()["error"]["code"] == "previous_response_not_found"
    assert err.envelope()["error"]["param"] is None


from app.services.chat.stream import ChatEvent
from app.services.responses.translate import ResponseAccumulator

ANSWER = ChatEvent("answer", {
    "answer": "คำตอบเต็ม",
    "summary": "สรุป",
    "references": [{"number": 1, "agency_id": "a-1", "agency_name": "กรมการปกครอง", "url": None}],
    "sections": [{"agencies": [{"id": "a-1"}]}],
    "errors": [],
})
DONE = ChatEvent("done", {"session_id": "s-1", "total_ms": 1200})


def _acc() -> ResponseAccumulator:
    return ResponseAccumulator(
        response_id="resp_11111111-1111-1111-1111-111111111111",
        model="onechat",
        conversation_id="c-1",
    )


def _drain(acc: ResponseAccumulator) -> list[dict]:
    events = [acc.created_event()]
    for chat_event in (ANSWER, DONE):
        events.extend(acc.consume(chat_event))
    return events


def test_full_event_sequence_and_order():
    assert [e["type"] for e in _drain(_acc())] == [
        "response.created",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ]


def test_sequence_numbers_are_zero_based_and_strictly_increasing():
    numbers = [e["sequence_number"] for e in _drain(_acc())]
    assert numbers == list(range(len(numbers)))


def test_the_delta_carries_the_whole_answer():
    delta = next(e for e in _drain(_acc()) if e["type"] == "response.output_text.delta")
    assert delta["delta"] == "คำตอบเต็ม"
    assert delta["output_index"] == 0
    assert delta["content_index"] == 0


def test_item_id_is_stable_across_the_stream():
    events = _drain(_acc())
    item_ids = {e["item_id"] for e in events if "item_id" in e}
    assert item_ids == {"msg_11111111-1111-1111-1111-111111111111"}


def test_completed_carries_the_final_response():
    completed = _drain(_acc())[-1]
    response = completed["response"]
    assert response["id"] == "resp_11111111-1111-1111-1111-111111111111"
    assert response["object"] == "response"
    assert response["status"] == "completed"
    assert response["model"] == "onechat"
    assert response["output_text"] == "คำตอบเต็ม"
    assert response["output"][0]["content"][0]["text"] == "คำตอบเต็ม"
    assert response["usage"] == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def test_portal_block_carries_the_v5_extras():
    portal = _drain(_acc())[-1]["response"]["portal"]
    assert portal["conversation_id"] == "c-1"
    assert portal["summary"] == "สรุป"
    assert portal["references"][0]["agency_name"] == "กรมการปกครอง"
    assert portal["agency_ids"] == ["a-1"]
    assert portal["cached"] is False
    assert portal["stream_version"] == "v5"


def test_cached_flag_is_reported():
    acc = ResponseAccumulator(
        response_id="resp_x", model="onechat", conversation_id="c-1", cached=True,
    )
    acc.created_event()
    acc.consume(ANSWER)
    assert acc.final_response()["portal"]["cached"] is True


def test_degrade_case_without_summary_still_completes():
    acc = _acc()
    acc.created_event()
    acc.consume(ChatEvent("answer", {"answer": "เฉพาะคำตอบ", "sections": [], "errors": []}))
    response = acc.final_response()
    assert response["output_text"] == "เฉพาะคำตอบ"
    assert response["portal"]["summary"] == ""
    assert response["portal"]["references"] == []


def test_pipeline_progress_events_produce_nothing():
    acc = _acc()
    acc.created_event()
    for name in ("step", "intent", "routing", "agency_start", "agency_responded", "agency_verified"):
        assert acc.consume(ChatEvent(name, {"whatever": True})) == []


def test_error_event_produces_response_failed():
    acc = _acc()
    acc.created_event()
    events = acc.consume(ChatEvent("error", {"message": "upstream exploded", "code": 502}))
    assert [e["type"] for e in events] == ["response.failed"]
    response = events[0]["response"]
    assert response["status"] == "failed"
    assert response["error"]["message"] == "upstream exploded"


def test_done_after_an_error_does_not_emit_completed():
    acc = _acc()
    acc.created_event()
    acc.consume(ChatEvent("error", {"message": "boom", "code": 500}))
    assert acc.consume(DONE) == []
