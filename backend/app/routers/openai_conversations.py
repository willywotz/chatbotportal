"""OpenAI-compatible Conversations + items API. Errors use ResponsesApiError."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from tortoise.expressions import Q

from app.auth.dependencies import get_current_user_non_ephemeral
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.openai_conversations import (
    ConversationCreateRequest,
    ConversationUpdateRequest,
    ItemsCreateRequest,
)
from app.services.openai.identity import owns
from app.services.openai.ids import conv_id, msg_id, parse_uuid
from app.services.openai.items import flatten_content, item_from_message, list_envelope
from app.services.openai.metadata import validate_metadata
from app.services.responses.errors import ResponsesApiError
from app.utils import now

router = APIRouter(prefix="/conversations", tags=["OpenAI Conversations"])

_MAX_ITEMS = 20
_MAX_LIMIT = 100


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
    user: User = Depends(get_current_user_non_ephemeral),
):
    metadata = validate_metadata(body.metadata)
    items = body.items or []
    if len(items) > _MAX_ITEMS:
        raise ResponsesApiError(f"`items` must not exceed {_MAX_ITEMS}.", param="items")
    conv = await Conversation.create(
        title="OpenAI conversation", metadata=metadata, user_id=user.id
    )
    if items:
        await _persist_items(items, conv.id, user.id)
    return JSONResponse(content=_conversation_object(conv))


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
    conversation_id: str, user: User = Depends(get_current_user_non_ephemeral)
):
    return _conversation_object(await _load_conversation(conversation_id, user))


@router.post("/{conversation_id}", summary="Update a conversation")
async def update_conversation(
    conversation_id: str, body: ConversationUpdateRequest,
    user: User = Depends(get_current_user_non_ephemeral),
):
    conv = await _load_conversation(conversation_id, user)
    conv.metadata = validate_metadata(body.metadata)
    await conv.save(update_fields=["metadata", "updated_at"])
    return _conversation_object(conv)


@router.delete("/{conversation_id}", summary="Delete a conversation")
async def delete_conversation(
    conversation_id: str, user: User = Depends(get_current_user_non_ephemeral)
):
    conv = await _load_conversation(conversation_id, user)
    stamp = now()
    conv.deleted_at = stamp
    await conv.save(update_fields=["deleted_at"])
    await Message.filter(conversation_id=conv.id, deleted_at=None).update(deleted_at=stamp)
    return {"id": conv_id(conv.id), "object": "conversation.deleted", "deleted": True}


async def _load_item(conv: Conversation, item_id: str) -> Message:
    mid = parse_uuid(item_id, "msg_", param="item_id", code="item_not_found")
    msg = await Message.get_or_none(id=mid, conversation_id=conv.id, deleted_at=None)
    if msg is None:
        raise ResponsesApiError(f"Item '{item_id}' not found",
                                 param="item_id", code="item_not_found", status=404)
    return msg


@router.post("/{conversation_id}/items", summary="Create items")
async def create_items(
    conversation_id: str, body: ItemsCreateRequest,
    include: list[str] | None = Query(None),
    user: User = Depends(get_current_user_non_ephemeral),
):
    conv = await _load_conversation(conversation_id, user)
    if len(body.items) > _MAX_ITEMS:
        raise ResponsesApiError(f"`items` must not exceed {_MAX_ITEMS}.", param="items")
    rows = await _persist_items(body.items, conv.id, conv.user_id)
    fresh = [await Message.get(id=r.id) for r in rows]
    return list_envelope([item_from_message(m) for m in fresh])


@router.get("/{conversation_id}/items", summary="List items")
async def list_items(
    conversation_id: str,
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    order: str = Query("desc"),
    after: str | None = Query(None),
    include: list[str] | None = Query(None),
    user: User = Depends(get_current_user_non_ephemeral),
):
    conv = await _load_conversation(conversation_id, user)
    asc = order == "asc"
    qs = Message.filter(conversation_id=conv.id, deleted_at=None)
    if after:
        cursor = await _load_item(conv, after)
        if asc:
            qs = qs.filter(
                Q(created_at__gt=cursor.created_at)
                | Q(created_at=cursor.created_at, id__gt=cursor.id)
            )
        else:
            qs = qs.filter(
                Q(created_at__lt=cursor.created_at)
                | Q(created_at=cursor.created_at, id__lt=cursor.id)
            )
    order_by = ["created_at", "id"] if asc else ["-created_at", "-id"]
    rows = await qs.order_by(*order_by).limit(limit + 1)
    has_more = len(rows) > limit
    return list_envelope([item_from_message(m) for m in rows[:limit]], has_more=has_more)


@router.get("/{conversation_id}/items/{item_id}", summary="Retrieve an item")
async def get_item(
    conversation_id: str, item_id: str,
    user: User = Depends(get_current_user_non_ephemeral),
):
    conv = await _load_conversation(conversation_id, user)
    return item_from_message(await _load_item(conv, item_id))


@router.delete("/{conversation_id}/items/{item_id}", summary="Delete an item")
async def delete_item(
    conversation_id: str, item_id: str,
    user: User = Depends(get_current_user_non_ephemeral),
):
    conv = await _load_conversation(conversation_id, user)
    msg = await _load_item(conv, item_id)
    msg.deleted_at = now()
    await msg.save(update_fields=["deleted_at"])
    return {"id": msg_id(msg.id), "object": "conversation.item.deleted", "deleted": True}
