from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from app.auth.keycloak import Principal
from app.errors import ApiError, ErrorCode
from app.models.conversation import Conversation, Message
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
from app.schemas.conversation import SaveConversationRequest

_READ_ALL_SCOPE = "conversation:read:all"


async def create_conversation(body: SaveConversationRequest, principal: Principal) -> Conversation:
    conv = await conversation_repo.create(
        title=body.title or "สนทนาใหม่",
        preview=body.preview or "",
        agencies=body.agencies,
        status=body.status,
        message_count=len(body.messages),
        response_time=body.response_time,
        user_id=principal.id,
    )

    if body.messages:
        msg_rows = [
            Message(
                id=m.id or uuid.uuid4(),
                conversation_id=conv.id,
                role=m.role,
                content=m.content,
                agent_steps=m.agent_steps or [],
                sources=m.sources or [],
                rating=m.rating,
                feedback_text=m.feedback_text,
                user_id=principal.id,
            )
            for m in body.messages
        ]
        await message_repo.bulk_create(msg_rows, ignore_conflicts=True)

    return conv


async def list_conversations(
    *,
    principal: Principal,
    search: str,
    filter_agency: str,
    date_from: str | None,
    date_to: str | None,
    page: int,
    page_size: int | None,
) -> tuple[list[Conversation], int]:
    """Search/filter conversations and return (page rows, full filtered total)."""
    created_from = None
    if date_from:
        try:
            created_from = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise ApiError(ErrorCode.INVALID_REQUEST, "date_from must be YYYY-MM-DD", status=400)
    created_to = None
    if date_to:
        try:
            created_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            raise ApiError(ErrorCode.INVALID_REQUEST, "date_to must be YYYY-MM-DD", status=400)

    return await conversation_repo.list_and_count(
        user_id=None if _READ_ALL_SCOPE in principal.scopes else principal.id,
        title_contains=search or None,
        agency_contains=filter_agency or None,
        created_from=created_from,
        created_to=created_to,
        offset=(page - 1) * page_size if page_size is not None else None,
        limit=page_size,
    )


async def _authorize(conversation_id: uuid.UUID, principal: Principal) -> Conversation:
    conv = await conversation_repo.by_id(conversation_id, exclude_deleted=True)
    if conv is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Conversation not found", status=404)
    if str(conv.user_id) != str(principal.id) and _READ_ALL_SCOPE not in principal.scopes:
        raise ApiError(ErrorCode.FORBIDDEN, "Forbidden", status=403)
    return conv


async def get_conversation_with_messages(conversation_id: uuid.UUID, principal: Principal) -> tuple[Conversation, list[Message]]:
    conv = await _authorize(conversation_id, principal)
    messages = await message_repo.list_for_conversation(conversation_id)
    return conv, messages


async def get_conversation_messages(conversation_id: uuid.UUID, principal: Principal) -> list[Message]:
    await _authorize(conversation_id, principal)
    return await message_repo.list_for_conversation(conversation_id)


async def delete_conversation(conversation_id: uuid.UUID, principal: Principal) -> None:
    conv = await conversation_repo.by_id(conversation_id)
    if conv is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Conversation not found", status=404)
    if str(conv.user_id) != str(principal.id) and _READ_ALL_SCOPE not in principal.scopes:
        raise ApiError(ErrorCode.FORBIDDEN, "Forbidden", status=403)
    await conversation_repo.delete(conv)
