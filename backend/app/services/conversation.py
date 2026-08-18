from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from tortoise.exceptions import DoesNotExist

from app.errors import ApiError, ErrorCode
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.conversation import SaveConversationRequest


async def create_conversation(body: SaveConversationRequest, user: User | None) -> Conversation:
    conv = await Conversation.create(
        title=body.title or "สนทนาใหม่",
        preview=body.preview or "",
        agencies=body.agencies,
        status=body.status,
        message_count=len(body.messages),
        response_time=body.response_time,
        user_id=user.id if user else None,
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
                user_id=user.id if user else None,
            )
            for m in body.messages
        ]
        await Message.bulk_create(msg_rows, ignore_conflicts=True)

    return conv


async def list_conversations(
    *,
    user: User,
    search: str,
    filter_agency: str,
    date_from: str | None,
    date_to: str | None,
    page: int,
    page_size: int | None,
) -> tuple[list[Conversation], int]:
    """Search/filter conversations and return (page rows, full filtered total)."""
    qs = Conversation.filter(deleted_at=None)

    if not user.is_admin:
        qs = qs.filter(user_id=user.id)

    if search:
        qs = qs.filter(title__icontains=search)

    if filter_agency:
        qs = qs.filter(agencies__contains=filter_agency)

    if date_from:
        try:
            qs = qs.filter(created_at__gte=datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            raise ApiError(ErrorCode.INVALID_REQUEST, "date_from must be YYYY-MM-DD", status=400)

    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            qs = qs.filter(created_at__lt=end)
        except ValueError:
            raise ApiError(ErrorCode.INVALID_REQUEST, "date_to must be YYYY-MM-DD", status=400)

    total = await qs.count()

    page_qs = qs.order_by("-created_at")
    if page_size is not None:
        page_qs = page_qs.offset((page - 1) * page_size).limit(page_size)
    rows = await page_qs

    return rows, total


async def _authorize(conversation_id: uuid.UUID, user: User) -> Conversation:
    conv = await Conversation.get_or_none(id=conversation_id, deleted_at=None)
    if conv is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Conversation not found", status=404)
    if str(conv.user_id) != str(user.id) and not user.is_admin:
        raise ApiError(ErrorCode.FORBIDDEN, "Forbidden", status=403)
    return conv


async def get_conversation_with_messages(conversation_id: uuid.UUID, user: User) -> tuple[Conversation, list[Message]]:
    conv = await _authorize(conversation_id, user)
    messages = await Message.filter(conversation_id=conversation_id, deleted_at=None).order_by("created_at")
    return conv, messages


async def get_conversation_messages(conversation_id: uuid.UUID, user: User) -> list[Message]:
    await _authorize(conversation_id, user)
    return await Message.filter(conversation_id=conversation_id, deleted_at=None).order_by("created_at")


async def delete_conversation(conversation_id: uuid.UUID, user: User) -> None:
    try:
        conv = await Conversation.get(id=conversation_id)
    except DoesNotExist:
        raise ApiError(ErrorCode.NOT_FOUND, "Conversation not found", status=404)
    if str(conv.user_id) != str(user.id) and not user.is_admin:
        raise ApiError(ErrorCode.FORBIDDEN, "Forbidden", status=403)
    await conv.delete()
