from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.chat.models.conversation import Message


async def by_id(session: AsyncSession, message_id) -> Message | None:
    return await session.get(Message, message_id)


async def list_for_conversation(
    session: AsyncSession, conversation_id, *, include_deleted: bool = False,
) -> list[Message]:
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if not include_deleted:
        stmt = stmt.where(Message.deleted_at.is_(None))
    stmt = stmt.order_by(Message.created_at)
    return list((await session.execute(stmt)).scalars().all())


async def first_user_message(session: AsyncSession, conversation_id) -> Message | None:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role == "user")
        .order_by(Message.created_at)
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def create(session: AsyncSession, **fields) -> Message:
    obj = Message(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def bulk_create(session: AsyncSession, rows, *, ignore_conflicts: bool = False) -> None:
    if ignore_conflicts:
        stmt = pg_insert(Message).values(rows).on_conflict_do_nothing()
    else:
        stmt = insert(Message).values(rows)
    await session.execute(stmt)


async def set_category(session: AsyncSession, message_id, category) -> None:
    await session.execute(update(Message).where(Message.id == message_id).values(category=category))


async def save(session: AsyncSession, message: Message, *, update_fields: list[str] | None = None) -> None:
    await session.flush()
