from __future__ import annotations

from app.models.conversation import Message


async def by_id(message_id) -> Message | None:
    return await Message.get_or_none(id=message_id)


async def list_for_conversation(conversation_id, *, include_deleted: bool = False) -> list[Message]:
    qs = Message.filter(conversation_id=conversation_id)
    if not include_deleted:
        qs = qs.filter(deleted_at=None)
    return await qs.order_by("created_at")


async def first_user_message(conversation_id) -> Message | None:
    return await (
        Message.filter(conversation_id=conversation_id, role="user")
        .order_by("created_at")
        .first()
    )


async def create(**fields) -> Message:
    return await Message.create(**fields)


async def bulk_create(rows, *, ignore_conflicts: bool = False) -> None:
    await Message.bulk_create(rows, ignore_conflicts=ignore_conflicts)


async def set_category(message_id, category) -> None:
    await Message.filter(id=message_id).update(category=category)


async def save(message: Message, *, update_fields: list[str] | None = None) -> None:
    await message.save(update_fields=update_fields)
