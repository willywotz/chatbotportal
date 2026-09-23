from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


async def by_id(session: AsyncSession, conversation_id, *, exclude_deleted: bool = False) -> Conversation | None:
    if not exclude_deleted:
        return await session.get(Conversation, conversation_id)
    stmt = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
    return (await session.execute(stmt)).scalars().first()


async def list_and_count(
    session: AsyncSession, *, user_id, title_contains: str | None, agency_contains: str | None,
    created_from, created_to, offset: int | None, limit: int | None,
) -> tuple[list[Conversation], int]:
    stmt = select(Conversation).where(Conversation.deleted_at.is_(None))
    if user_id is not None:
        stmt = stmt.where(Conversation.user_id == user_id)
    if title_contains:
        stmt = stmt.where(Conversation.title.ilike(f"%{title_contains}%"))
    if agency_contains:
        stmt = stmt.where(Conversation.agencies.contains([agency_contains]))
    if created_from is not None:
        stmt = stmt.where(Conversation.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Conversation.created_at < created_to)
    total = (await session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )).scalar_one()
    page_stmt = stmt.order_by(Conversation.created_at.desc())
    if limit is not None:
        page_stmt = page_stmt.offset(offset or 0).limit(limit)
    rows = (await session.execute(page_stmt)).scalars().all()
    return list(rows), total


async def create(session: AsyncSession, **fields) -> Conversation:
    obj = Conversation(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def save(session: AsyncSession, conv: Conversation, *, update_fields: list[str] | None = None) -> None:
    await session.flush()


async def delete(session: AsyncSession, conv: Conversation) -> None:
    await session.delete(conv)
