"""Golden question and eval result data access, scoped to one agency."""

import uuid

from fastapi import HTTPException, status

from app.models.agency import Agency
from app.models.evaluation import EvalResult, GoldenQuestion


async def create_golden_question(agency: Agency, question: str, expected_topics: list[str]) -> GoldenQuestion:
    return await GoldenQuestion.create(agency=agency, question=question, expected_topics=expected_topics)


async def list_golden_questions(agency: Agency) -> list[GoldenQuestion]:
    return await GoldenQuestion.filter(agency=agency)


async def delete_golden_question(agency: Agency, gq_id: uuid.UUID) -> None:
    gq = await GoldenQuestion.get_or_none(id=gq_id, agency=agency)
    if gq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden question not found")
    await gq.delete()


async def list_eval_results(agency: Agency, limit: int) -> list[EvalResult]:
    question_ids = await GoldenQuestion.filter(agency=agency).values_list("id", flat=True)
    return await EvalResult.filter(golden_question_id__in=list(question_ids)).order_by("-created_at").limit(limit)
