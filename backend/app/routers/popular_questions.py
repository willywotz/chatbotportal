"""Popular Questions API.

``GET /public/popular-questions`` is anonymous (no auth dependency at all —
mirrors ``app/routers/public_status.py`` so it passes the global role
chokepoint untouched). Everything under ``/popular-questions`` is admin CRUD.
"""
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_scope
from app.auth.principal import Principal
from app.db import get_db
from app.schemas.popular_question import (
    PopularQuestionCreate,
    PopularQuestionListResponse,
    PopularQuestionResponse,
    PopularQuestionUpdate,
)
from app.services.popular_questions import (
    create_question,
    delete_question,
    list_questions,
    published_questions,
    regenerate,
    to_response,
    update_question,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Popular Questions"])


@router.get("/public/popular-questions", summary="Public popular questions")
async def get_public_popular_questions(session: AsyncSession = Depends(get_db)) -> dict:
    return {"data": await published_questions(session)}


@router.get(
    "/popular-questions",
    response_model=PopularQuestionListResponse,
    dependencies=[Security(require_scope, scopes=["popular:read"])],
    summary="List all popular questions (admin)",
)
async def list_popular_questions(session: AsyncSession = Depends(get_db)):
    rows = await list_questions(session)
    data = [await to_response(session, r) for r in rows]
    return PopularQuestionListResponse(data=data, total=len(data))


@router.post(
    "/popular-questions",
    response_model=PopularQuestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual popular question",
)
async def create_popular_question(
    body: PopularQuestionCreate,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["popular:write"]),
):
    pq = await create_question(session, body)
    return await to_response(session, pq)


@router.patch(
    "/popular-questions/{question_id}",
    response_model=PopularQuestionResponse,
    summary="Partial update a popular question",
)
async def update_popular_question(
    question_id: uuid.UUID,
    body: PopularQuestionUpdate,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["popular:write"]),
):
    pq = await update_question(session, question_id, body)
    return await to_response(session, pq)


@router.delete(
    "/popular-questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a popular question",
)
async def delete_popular_question(
    question_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["popular:write"]),
):
    await delete_question(session, question_id)


async def _regenerate_in_background() -> None:
    """Own short-lived session — runs after the request's session has closed."""
    import app.db as db

    async with db.AsyncSessionLocal() as session, session.begin():
        await regenerate(session)


@router.post(
    "/popular-questions/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger popular questions regeneration",
)
async def trigger_regenerate(background_tasks: BackgroundTasks, _: Principal = Security(require_scope, scopes=["popular:write"])):
    background_tasks.add_task(_regenerate_in_background)
    return {"status": "scheduled"}
