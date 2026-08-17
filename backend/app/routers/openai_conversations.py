"""OpenAI-compatible Conversations + items API. Errors use ResponsesApiError."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user_non_ephemeral
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.openai_conversations import (
    ConversationCreateRequest,
    ConversationUpdateRequest,
    ItemsCreateRequest,
)
from app.services.openai import conversations as conversation_service
from app.services.openai.ids import conv_id, msg_id
from app.services.openai.items import item_from_message, list_envelope
from app.services.openai.metadata import validate_metadata
from app.services.responses.errors import ResponsesApiError

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


@router.post("", summary="Create a conversation")
async def create_conversation(
    body: ConversationCreateRequest,
    user: User = Depends(get_current_user_non_ephemeral),
):
    metadata = validate_metadata(body.metadata)
    items = body.items or []
    if len(items) > _MAX_ITEMS:
        raise ResponsesApiError(f"`items` must not exceed {_MAX_ITEMS}.", param="items")
    conv = await conversation_service.create_conversation(metadata, user.id)
    if items:
        await conversation_service.persist_items(items, conv.id, user.id)
    return JSONResponse(content=_conversation_object(conv))


@router.get("/{conversation_id}", summary="Retrieve a conversation")
async def get_conversation(
    conversation_id: str, user: User = Depends(get_current_user_non_ephemeral)
):
    conv = await conversation_service.load_conversation(conversation_id, user)
    return _conversation_object(conv)


@router.post("/{conversation_id}", summary="Update a conversation")
async def update_conversation(
    conversation_id: str, body: ConversationUpdateRequest,
    user: User = Depends(get_current_user_non_ephemeral),
):
    conv = await conversation_service.load_conversation(conversation_id, user)
    await conversation_service.update_metadata(conv, validate_metadata(body.metadata))
    return _conversation_object(conv)


@router.delete("/{conversation_id}", summary="Delete a conversation")
async def delete_conversation(
    conversation_id: str, user: User = Depends(get_current_user_non_ephemeral)
):
    conv = await conversation_service.load_conversation(conversation_id, user)
    await conversation_service.soft_delete_conversation(conv)
    return {"id": conv_id(conv.id), "object": "conversation.deleted", "deleted": True}


@router.post("/{conversation_id}/items", summary="Create items")
async def create_items(
    conversation_id: str, body: ItemsCreateRequest,
    include: list[str] | None = Query(None),
    user: User = Depends(get_current_user_non_ephemeral),
):
    conv = await conversation_service.load_conversation(conversation_id, user)
    if len(body.items) > _MAX_ITEMS:
        raise ResponsesApiError(f"`items` must not exceed {_MAX_ITEMS}.", param="items")
    fresh = await conversation_service.create_items(conv, body.items)
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
    conv = await conversation_service.load_conversation(conversation_id, user)
    cursor = await conversation_service.load_item(conv, after) if after else None
    rows, has_more = await conversation_service.list_items(
        conv, limit=limit, order=order, after_cursor=cursor
    )
    return list_envelope([item_from_message(m) for m in rows], has_more=has_more)


@router.get("/{conversation_id}/items/{item_id}", summary="Retrieve an item")
async def get_item(
    conversation_id: str, item_id: str,
    user: User = Depends(get_current_user_non_ephemeral),
):
    conv = await conversation_service.load_conversation(conversation_id, user)
    return item_from_message(await conversation_service.load_item(conv, item_id))


@router.delete("/{conversation_id}/items/{item_id}", summary="Delete an item")
async def delete_item(
    conversation_id: str, item_id: str,
    user: User = Depends(get_current_user_non_ephemeral),
):
    conv = await conversation_service.load_conversation(conversation_id, user)
    msg = await conversation_service.load_item(conv, item_id)
    await conversation_service.delete_item(msg)
    return {"id": msg_id(msg.id), "object": "conversation.item.deleted", "deleted": True}
