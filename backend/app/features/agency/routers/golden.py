import uuid

from fastapi import APIRouter, Depends, Query, Security, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.dependencies import require_scope
from app.core.security.principal import Principal
from app.core.db import get_db
from app.features.agency.services import agency as agency_service
from app.features.agency.services import agency_golden

router = APIRouter()


class GoldenQuestionCreate(BaseModel):
    question: str
    expected_topics: list[str] = []


class GoldenQuestionResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    question: str
    expected_topics: list[str]

    model_config = {"from_attributes": True}


class EvalResultResponse(BaseModel):
    id: uuid.UUID
    golden_question_id: uuid.UUID
    score: float
    answer: str
    judge_reason: str

    model_config = {"from_attributes": True}


@router.post(
    "/{agency_id}/golden-questions",
    response_model=GoldenQuestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a golden question for an agency (admin)",
)
async def create_golden_question(
    agency_id: str,
    body: GoldenQuestionCreate,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["agency:write"]),
) -> GoldenQuestionResponse:
    agency = await agency_service.get_agency_or_404(session, agency_id)
    gq = await agency_golden.create_golden_question(session, agency, body.question, body.expected_topics)
    return GoldenQuestionResponse(id=gq.id, agency_id=agency.id, question=gq.question, expected_topics=gq.expected_topics)


@router.get(
    "/{agency_id}/golden-questions",
    response_model=list[GoldenQuestionResponse],
    summary="List golden questions for an agency (admin)",
)
async def list_golden_questions(
    agency_id: str,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["agency:read"]),
) -> list[GoldenQuestionResponse]:
    agency = await agency_service.get_agency_or_404(session, agency_id)
    questions = await agency_golden.list_golden_questions(session, agency)
    return [
        GoldenQuestionResponse(id=q.id, agency_id=agency.id, question=q.question, expected_topics=q.expected_topics)
        for q in questions
    ]


@router.delete(
    "/{agency_id}/golden-questions/{gq_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a golden question (admin)",
)
async def delete_golden_question(
    agency_id: str,
    gq_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["agency:write"]),
) -> None:
    agency = await agency_service.get_agency_or_404(session, agency_id)
    await agency_golden.delete_golden_question(session, agency, gq_id)


@router.get(
    "/{agency_id}/eval-results",
    response_model=list[EvalResultResponse],
    summary="Recent eval results for an agency's golden questions (admin)",
)
async def list_eval_results(
    agency_id: str,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["agency:read"]),
) -> list[EvalResultResponse]:
    agency = await agency_service.get_agency_or_404(session, agency_id)
    results = await agency_golden.list_eval_results(session, agency, limit)
    return [
        EvalResultResponse(
            id=r.id,
            golden_question_id=r.golden_question_id,
            score=r.score,
            answer=r.answer,
            judge_reason=r.judge_reason,
        )
        for r in results
    ]
