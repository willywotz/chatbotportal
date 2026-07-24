"""OpenAI-compatible Conversations + items API. Errors use ResponsesApiError."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user_optional
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.openai_conversations import (
    ConversationCreateRequest,
    ConversationUpdateRequest,
)
from app.services.openai.identity import owner_or_ephemeral, owns
from app.services.openai.ids import conv_id, parse_uuid
from app.services.openai.items import flatten_content
from app.services.openai.metadata import validate_metadata
from app.services.responses.errors import ResponsesApiError
from app.utils import now

router = APIRouter(prefix="/conversations", tags=["OpenAI Conversations"])

_MAX_ITEMS = 20


def _conversation_object(conv: Conversation) -> dict:
    return {
        "id": conv_id(conv.id),
        "object": "conversation",
        "created_at": int(conv.created_at.timestamp()),
        "metadata": conv.metadata or {},
    }


async def _persist_items(items, conversation_id, owner_id) -> list[Message]:
    rows = [
        Message(conversation_id=conversation_id, role=i.role,
                content=flatten_content(i.content), user_id=owner_id)
        for i in items
    ]
    await Message.bulk_create(rows)
    return rows


@router.post("", summary="Create a conversation")
async def create_conversation(
    body: ConversationCreateRequest,
    user: User | None = Depends(get_current_user_optional),
):
    metadata = validate_metadata(body.metadata)
    items = body.items or []
    if len(items) > _MAX_ITEMS:
        raise ResponsesApiError(f"`items` must not exceed {_MAX_ITEMS}.", param="items")
    owner, token = await owner_or_ephemeral(user)
    conv = await Conversation.create(
        title="OpenAI conversation", metadata=metadata, user_id=owner.id
    )
    if items:
        await _persist_items(items, conv.id, owner.id)
    resp = JSONResponse(content=_conversation_object(conv))
    if token:
        resp.headers["X-Portal-Session"] = token
    return resp


async def _load_conversation(conversation_id: str, user: User | None) -> Conversation:
    cid = parse_uuid(conversation_id, "conv_", param="conversation_id",
                      code="conversation_not_found")
    conv = await Conversation.get_or_none(id=cid, deleted_at=None)
    if conv is None or not owns(conv, user):
        raise ResponsesApiError(
            f"Conversation '{conversation_id}' not found",
            param="conversation_id", code="conversation_not_found", status=404,
        )
    return conv


@router.get("/{conversation_id}", summary="Retrieve a conversation")
async def get_conversation(
    conversation_id: str, user: User | None = Depends(get_current_user_optional)
):
    return _conversation_object(await _load_conversation(conversation_id, user))


@router.post("/{conversation_id}", summary="Update a conversation")
async def update_conversation(
    conversation_id: str, body: ConversationUpdateRequest,
    user: User | None = Depends(get_current_user_optional),
):
    conv = await _load_conversation(conversation_id, user)
    conv.metadata = validate_metadata(body.metadata)
    await conv.save(update_fields=["metadata", "updated_at"])
    return _conversation_object(conv)


@router.delete("/{conversation_id}", summary="Delete a conversation")
async def delete_conversation(
    conversation_id: str, user: User | None = Depends(get_current_user_optional)
):
    conv = await _load_conversation(conversation_id, user)
    stamp = now()
    conv.deleted_at = stamp
    await conv.save(update_fields=["deleted_at"])
    await Message.filter(conversation_id=conv.id, deleted_at=None).update(deleted_at=stamp)
    return {"id": conv_id(conv.id), "object": "conversation.deleted", "deleted": True}
