"""Popular Questions API.

``GET /public/popular-questions`` is anonymous (no auth dependency at all —
mirrors ``app/routers/public_status.py`` so it passes the global role
chokepoint untouched). Everything under ``/popular-questions`` is admin CRUD.
"""
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.auth.dependencies import require_admin
from app.models.user import User
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
async def get_public_popular_questions() -> dict:
    return {"data": await published_questions()}


@router.get(
    "/popular-questions",
    response_model=PopularQuestionListResponse,
    dependencies=[Depends(require_admin)],
    summary="List all popular questions (admin)",
)
async def list_popular_questions():
    rows = await list_questions()
    data = [await to_response(r) for r in rows]
    return PopularQuestionListResponse(data=data, total=len(data))


@router.post(
    "/popular-questions",
    response_model=PopularQuestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual popular question",
)
async def create_popular_question(body: PopularQuestionCreate, _: User = Depends(require_admin)):
    pq = await create_question(body)
    return await to_response(pq)


@router.patch(
    "/popular-questions/{question_id}",
    response_model=PopularQuestionResponse,
    summary="Partial update a popular question",
)
async def update_popular_question(question_id: uuid.UUID, body: PopularQuestionUpdate, _: User = Depends(require_admin)):
    pq = await update_question(question_id, body)
    return await to_response(pq)


@router.delete(
    "/popular-questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a popular question",
)
async def delete_popular_question(question_id: uuid.UUID, _: User = Depends(require_admin)):
    await delete_question(question_id)


@router.post(
    "/popular-questions/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger popular questions regeneration",
)
async def trigger_regenerate(background_tasks: BackgroundTasks, _: User = Depends(require_admin)):
    background_tasks.add_task(regenerate)
    return {"status": "scheduled"}
