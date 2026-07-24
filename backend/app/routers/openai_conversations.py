"""OpenAI-compatible Conversations + items API. Errors use ResponsesApiError."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user_optional
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.openai_conversations import ConversationCreateRequest
from app.services.openai.identity import owner_or_ephemeral
from app.services.openai.ids import conv_id
from app.services.openai.items import flatten_content
from app.services.openai.metadata import validate_metadata
from app.services.responses.errors import ResponsesApiError

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
