from __future__ import annotations

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, insert, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.chat.models.conversation import Conversation, Message
from app.features.analytics.models.popular_question import PopularQuestion, PopularQuestionSource


async def by_id(session: AsyncSession, question_id) -> PopularQuestion | None:
    return await session.get(PopularQuestion, question_id)


async def visible_with_agency(session: AsyncSession) -> list[PopularQuestion]:
    stmt = (
        select(PopularQuestion)
        .options(selectinload(PopularQuestion.agency))
        .where(PopularQuestion.hidden.is_(False))
    )
    return list((await session.execute(stmt)).scalars().all())


async def all_with_agency(session: AsyncSession) -> list[PopularQuestion]:
    stmt = select(PopularQuestion).options(selectinload(PopularQuestion.agency))
    return list((await session.execute(stmt)).scalars().all())


async def text_key_exists(session: AsyncSession, text_key: str, *, exclude_id=None) -> bool:
    stmt = select(literal(True)).where(PopularQuestion.text_key == text_key)
    if exclude_id is not None:
        stmt = stmt.where(PopularQuestion.id != exclude_id)
    return (await session.execute(stmt.limit(1))).scalar() is not None


async def delete_stale_auto(session: AsyncSession) -> None:
    """Drop unpinned, unhidden auto-generated rows ahead of a regenerate pass."""
    stmt = sa_delete(PopularQuestion).where(
        PopularQuestion.source == PopularQuestionSource.auto,
        PopularQuestion.pinned.is_(False),
        PopularQuestion.hidden.is_(False),
    )
    await session.execute(stmt)


async def recent_successful_turn_count(session: AsyncSession, cutoff) -> int:
    stmt = (
        select(func.count())
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.role == "user", Message.created_at >= cutoff, Conversation.status == "success")
    )
    return (await session.execute(stmt)).scalar_one()


async def recent_successful_user_messages(session: AsyncSession, cutoff, limit: int) -> list[dict]:
    stmt = (
        select(Message.id, Message.content)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.role == "user", Message.created_at >= cutoff, Conversation.status == "success")
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [{"id": r.id, "content": r.content} for r in rows]


async def assistant_replies_for(session: AsyncSession, parent_ids) -> list[dict]:
    stmt = select(Message.parent_id, Message.agency_ids).where(
        Message.role == "assistant", Message.parent_id.in_(parent_ids),
    )
    rows = (await session.execute(stmt)).all()
    return [{"parent_id": r.parent_id, "agency_ids": r.agency_ids} for r in rows]


async def create(session: AsyncSession, **fields) -> PopularQuestion:
    obj = PopularQuestion(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def update(session: AsyncSession, obj: PopularQuestion, data: dict) -> PopularQuestion:
    for key, value in data.items():
        setattr(obj, key, value)
    await session.flush()
    return obj


async def delete(session: AsyncSession, obj: PopularQuestion) -> None:
    await session.delete(obj)


async def bulk_create(session: AsyncSession, rows, *, ignore_conflicts: bool = False) -> None:
    if ignore_conflicts:
        stmt = pg_insert(PopularQuestion).values(rows).on_conflict_do_nothing()
    else:
        stmt = insert(PopularQuestion).values(rows)
    await session.execute(stmt)
