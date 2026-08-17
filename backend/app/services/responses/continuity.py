"""Conversation continuity for the OpenAI-compatible surface.

A response id is `resp_<assistant message uuid>`, so a continuation resolves by
loading that message and reading its conversation. A WebSocket may pass a
connection-local cache to skip the query for the most recent response, matching
OpenAI's connection-local semantics.
"""
import uuid

from app.models.conversation import Message
from app.services.responses.errors import ResponsesApiError
from app.utils import generate_uuid

RESPONSE_ID_PREFIX = "resp_"


def response_id_for(assistant_message_id) -> str:
    return f"{RESPONSE_ID_PREFIX}{assistant_message_id}"


def _same_conversation(resolved: str, conversation: str) -> bool:
    """Compare as UUIDs so textual case doesn't cause a spurious conflict."""
    try:
        return uuid.UUID(resolved) == uuid.UUID(conversation)
    except ValueError:
        return False


def _not_found(previous_response_id: str) -> ResponsesApiError:
    return ResponsesApiError(
        f"Previous response with id '{previous_response_id}' not found",
        type="invalid_request_error",
        param="previous_response_id",
        code="previous_response_not_found",
        status=404,
    )


async def resolve_conversation(
    *,
    previous_response_id: str | None,
    conversation: str | None,
    cache: dict[str, str] | None = None,
) -> tuple[str, bool]:
    resolved: str | None = None

    if previous_response_id:
        if cache is not None and previous_response_id in cache:
            resolved = cache[previous_response_id]
        else:
            raw = previous_response_id.removeprefix(RESPONSE_ID_PREFIX)
            try:
                message_id = uuid.UUID(raw)
            except ValueError:
                raise _not_found(previous_response_id)
            message = await Message.filter(
                id=message_id, role="assistant", deleted_at=None
            ).first()
            if message is None:
                raise _not_found(previous_response_id)
            resolved = str(message.conversation_id)

    if conversation:
        conversation = conversation.removeprefix("conv_")
        if resolved is not None and not _same_conversation(resolved, conversation):
            raise ResponsesApiError(
                "`conversation` does not match the conversation of "
                "`previous_response_id`; supply only one.",
                param="conversation",
            )
        if resolved is None:
            resolved = conversation

    if resolved is None:
        return str(generate_uuid()), False
    return resolved, True
