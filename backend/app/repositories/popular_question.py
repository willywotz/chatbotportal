from __future__ import annotations

from sqlalchemy import insert, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.popular_question import PopularQuestion


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


async def text_key_exists(session: AsyncSession, text_key: str) -> bool:
    stmt = select(literal(True)).where(PopularQuestion.text_key == text_key).limit(1)
    return (await session.execute(stmt)).scalar() is not None


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
