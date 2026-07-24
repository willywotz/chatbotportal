"""Reconstruct a Response object and its input_items from a stored Message."""
from app.models.conversation import Message
from app.services.openai.identity import owns
from app.services.openai.ids import parse_uuid
from app.services.openai.items import item_from_message, list_envelope
from app.services.responses.errors import ResponsesApiError

_ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def _not_found(response_id: str) -> ResponsesApiError:
    return ResponsesApiError(f"Response with id '{response_id}' not found",
                             param="response_id", code="response_not_found", status=404)


async def load_assistant_message(response_id: str, user) -> Message:
    try:
        mid = parse_uuid(response_id, "resp_", param="response_id", code="response_not_found")
    except ResponsesApiError:
        raise _not_found(response_id)
    msg = await Message.get_or_none(id=mid, role="assistant", deleted_at=None)
    if msg is None or not owns(msg, user):
        raise _not_found(response_id)
    return msg


def response_object(msg) -> dict:
    answer = (msg.content or "").strip()
    summary = (msg.summary or "").strip()
    body = {
        "id": f"resp_{msg.id}",
        "object": "response",
        "created_at": int(msg.created_at.timestamp()),
        "status": "completed",
        "model": "thai-citizen-guide",  # not persisted per-turn; echo the default id
        "output": [],
        "output_text": answer,
        "usage": dict(_ZERO_USAGE),
        "portal": {
            "conversation_id": str(msg.conversation_id),
            "summary": summary,
            "references": msg.summary_references or [],
            "agency_ids": msg.agency_ids or [],
            "cached": False,                        # not persisted; best-effort
            "stream_version": "v5" if summary else "v4",
        },
    }
    if answer:
        body["output"] = [{
            "id": f"msg_{msg.id}", "type": "message", "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": answer, "annotations": []}],
        }]
    return body


async def input_items(msg, *, order: str, limit: int) -> dict:
    prior = (await Message.filter(conversation_id=msg.conversation_id, role="user",
                                  deleted_at=None, created_at__lt=msg.created_at)
             .order_by("-created_at").first())
    return list_envelope([item_from_message(prior)] if prior else [])
