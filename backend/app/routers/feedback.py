"""
Feedback stats route — port of the Supabase `feedback-stats` edge function.

Endpoint
--------
  GET  /feedback/stats
"""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user, require_admin
from app.models.user import User
from app.schemas.conversation import FeedbackStats
from app.services.feedback import agency_low_rated, agency_low_rated_or_404, get_feedback_stats
from app.services.feedback import scalar_stats as _scalar_stats

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.get("/agencies/{agency_id}/low-rated", summary="Down-rated answers for an agency (admin)")
async def get_agency_low_rated(agency_id: str, _: User = Depends(require_admin)):
    return await agency_low_rated_or_404(agency_id)


@router.get("/stats", response_model=FeedbackStats, summary="Get feedback and satisfaction metrics")
async def feedback_stats(_user: User = Depends(get_current_user)) -> FeedbackStats:
    # Authorization is enforced by the global role allowlist: admin passes it;
    # a plain `user` is blocked upstream.
    return await get_feedback_stats()
