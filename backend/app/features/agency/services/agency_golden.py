import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode
from app.features.agency.models.agency import Agency
from app.features.agency.models.evaluation import EvalResult, GoldenQuestion
from app.features.agency.repositories import evaluation as evaluation_repo


async def create_golden_question(
    session: AsyncSession, agency: Agency, question: str, expected_topics: list[str]
) -> GoldenQuestion:
    return await evaluation_repo.create_golden(
        session, agency_id=agency.id, question=question, expected_topics=expected_topics
    )


async def list_golden_questions(session: AsyncSession, agency: Agency) -> list[GoldenQuestion]:
    return await evaluation_repo.list_golden_by_agency(session, agency.id)


async def delete_golden_question(session: AsyncSession, agency: Agency, gq_id: uuid.UUID) -> None:
    gq = await evaluation_repo.get_golden(session, gq_id, agency.id)
    if gq is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Golden question not found", status=404)
    await evaluation_repo.delete_golden(session, gq)


async def list_eval_results(session: AsyncSession, agency: Agency, limit: int) -> list[EvalResult]:
    questions = await evaluation_repo.list_golden_by_agency(session, agency.id)
    question_ids = [q.id for q in questions]
    return await evaluation_repo.list_eval_results(session, question_ids, limit)
