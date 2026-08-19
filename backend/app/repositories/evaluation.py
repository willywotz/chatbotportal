from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.evaluation import EvalResult, GoldenQuestion


async def all_golden_with_agency(session: AsyncSession) -> list[GoldenQuestion]:
    stmt = select(GoldenQuestion).options(selectinload(GoldenQuestion.agency))
    return list((await session.execute(stmt)).scalars().all())


async def create_golden(
    session: AsyncSession, *, agency_id: uuid.UUID, question: str, expected_topics: list[str]
) -> GoldenQuestion:
    obj = GoldenQuestion(agency_id=agency_id, question=question, expected_topics=expected_topics)
    session.add(obj)
    await session.flush()
    return obj


async def list_golden_by_agency(session: AsyncSession, agency_id: uuid.UUID) -> list[GoldenQuestion]:
    stmt = select(GoldenQuestion).where(GoldenQuestion.agency_id == agency_id)
    return list((await session.execute(stmt)).scalars().all())


async def get_golden(
    session: AsyncSession, gq_id: uuid.UUID, agency_id: uuid.UUID
) -> GoldenQuestion | None:
    stmt = select(GoldenQuestion).where(GoldenQuestion.id == gq_id, GoldenQuestion.agency_id == agency_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete_golden(session: AsyncSession, golden_question: GoldenQuestion) -> None:
    await session.delete(golden_question)


async def list_eval_results(
    session: AsyncSession, golden_question_ids: list[uuid.UUID], limit: int
) -> list[EvalResult]:
    stmt = (
        select(EvalResult)
        .where(EvalResult.golden_question_id.in_(golden_question_ids))
        .order_by(EvalResult.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
