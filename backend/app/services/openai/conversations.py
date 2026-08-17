"""Conversation + item persistence for the OpenAI-compatible Conversations API."""
from tortoise.expressions import Q

from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.openai.identity import owns
from app.services.openai.ids import parse_uuid
from app.services.openai.items import flatten_content
from app.services.responses.errors import ResponsesApiError
from app.utils import now


async def persist_items(items, conversation_id, owner_id) -> list[Message]:
    rows = [
        Message(conversation_id=conversation_id, role=i.role,
                content=flatten_content(i.content), user_id=owner_id)
        for i in items
    ]
    await Message.bulk_create(rows)
    return rows


async def create_conversation(metadata: dict, user_id) -> Conversation:
    return await Conversation.create(title="OpenAI conversation", metadata=metadata, user_id=user_id)


async def load_conversation(conversation_id: str, user: User | None) -> Conversation:
    cid = parse_uuid(conversation_id, "conv_", param="conversation_id",
                      code="conversation_not_found")
    conv = await Conversation.get_or_none(id=cid, deleted_at=None)
    if conv is None or not owns(conv, user):
        raise ResponsesApiError(
            f"Conversation '{conversation_id}' not found",
            param="conversation_id", code="conversation_not_found", status=404,
        )
    return conv


async def update_metadata(conv: Conversation, metadata: dict) -> None:
    conv.metadata = metadata
    await conv.save(update_fields=["metadata", "updated_at"])


async def soft_delete_conversation(conv: Conversation) -> None:
    stamp = now()
    conv.deleted_at = stamp
    await conv.save(update_fields=["deleted_at"])
    await Message.filter(conversation_id=conv.id, deleted_at=None).update(deleted_at=stamp)


async def load_item(conv: Conversation, item_id: str) -> Message:
    mid = parse_uuid(item_id, "msg_", param="item_id", code="item_not_found")
    msg = await Message.get_or_none(id=mid, conversation_id=conv.id, deleted_at=None)
    if msg is None:
        raise ResponsesApiError(f"Item '{item_id}' not found",
                                 param="item_id", code="item_not_found", status=404)
    return msg


async def create_items(conv: Conversation, items) -> list[Message]:
    rows = await persist_items(items, conv.id, conv.user_id)
    return [await Message.get(id=r.id) for r in rows]


async def list_items(
    conv: Conversation, *, limit: int, order: str, after_cursor: Message | None
) -> tuple[list[Message], bool]:
    asc = order == "asc"
    qs = Message.filter(conversation_id=conv.id, deleted_at=None)
    if after_cursor:
        if asc:
            qs = qs.filter(
                Q(created_at__gt=after_cursor.created_at)
                | Q(created_at=after_cursor.created_at, id__gt=after_cursor.id)
            )
        else:
            qs = qs.filter(
                Q(created_at__lt=after_cursor.created_at)
                | Q(created_at=after_cursor.created_at, id__lt=after_cursor.id)
            )
    order_by = ["created_at", "id"] if asc else ["-created_at", "-id"]
    rows = await qs.order_by(*order_by).limit(limit + 1)
    has_more = len(rows) > limit
    return rows[:limit], has_more


async def delete_item(msg: Message) -> None:
    msg.deleted_at = now()
    await msg.save(update_fields=["deleted_at"])
