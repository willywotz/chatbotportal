"""
Feedback stats route — port of the Supabase `feedback-stats` edge function.

Endpoint
--------
  GET  /feedback/statistics
"""

from fastapi import APIRouter, Depends, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_scope
from app.auth.keycloak import Principal
from app.db import get_db
from app.schemas.conversation import FeedbackStats
from app.services.feedback import agency_low_rated, agency_low_rated_or_404, get_feedback_stats
from app.services.feedback import scalar_stats as _scalar_stats

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.get("/agencies/{agency_id}/low-rated", summary="Down-rated answers for an agency")
async def get_agency_low_rated(
    agency_id: str,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["feedback:read:detail"]),
):
    return await agency_low_rated_or_404(session, agency_id)


@router.get("/statistics", response_model=FeedbackStats, summary="Get feedback and satisfaction metrics")
async def feedback_stats(
    session: AsyncSession = Depends(get_db),
    _user: Principal = Security(require_scope, scopes=["feedback:read"]),
) -> FeedbackStats:
    return await get_feedback_stats(session)
