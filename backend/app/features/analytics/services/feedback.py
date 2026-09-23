from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ApiError, ErrorCode
from app.features.chat.models.conversation import Message
from app.features.agency.repositories import agency as agency_repo
from app.features.analytics.repositories import feedback_read as feedback_repo
from app.features.chat.schemas.conversation import FeedbackStats
from app.core.utils import clean_agency_ids, now


async def agency_low_rated(session: AsyncSession, agency_id: str, limit: int = 50) -> list[dict]:
    """Recent down-rated assistant answers involving an agency.

    `agency_ids` is a JSON list; matching membership is filtered in Python
    after fetching the most recent down-rated assistant messages. The
    `limit` caps the DB query BEFORE the Python membership filter, so the
    result may contain fewer than `limit` rows for this agency. That is
    acceptable for a "recent low-rated" view.
    """
    rows = await feedback_repo.low_rated_assistant_messages(session, limit)
    out = [m for m in rows if agency_id in clean_agency_ids(m.agency_ids)]
    return [
        {"id": str(m.id), "content": m.content, "feedback_text": m.feedback_text,
         "created_at": str(m.created_at)}
        for m in out
    ]


async def agency_low_rated_or_404(session: AsyncSession, agency_id: str, limit: int = 50) -> list[dict]:
    if await agency_repo.by_id(session, agency_id) is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Agency not found", status=404)
    return await agency_low_rated(session, agency_id, limit)


def scalar_stats(message_state: list[dict]) -> tuple[int, int, int, int]:
    """Coalesce the ungrouped rating aggregate into (total, up, down, rate%).

    An aggregate with no GROUP BY yields one row even over zero rated messages,
    where AVG(...) and the SUM(...)s come back as SQL NULL. Any None becomes 0.
    """
    row = message_state[0] if message_state else {}
    return (
        row.get("total_rating") or 0,
        row.get("rating_up") or 0,
        row.get("rating_down") or 0,
        int(row.get("rate") or 0),
    )


async def get_feedback_stats(session: AsyncSession) -> FeedbackStats:
    totals = await feedback_repo.rating_totals(session)

    since = now() - timedelta(days=settings.FEEDBACK_TREND_DAYS)
    daily_trend = await feedback_repo.rating_daily_trend(session, since)
    for row in daily_trend:
        # rating_daily_trend does not compute a per-day rate; DailyTrendItem requires the key.
        row["rate"] = 0

    agencies = await feedback_repo.list_agencies_short_names(session)

    agency_breakdown = []
    for ag in agencies:
        counts = await feedback_repo.agency_rating_counts(session, ag["id"])
        agency_breakdown.append({
            "agency": ag["short_name"],
            "up": counts.get("rating_up") or 0,
            "down": counts.get("rating_down") or 0,
            "rate": 0,
        })

    raw_low_rated = await feedback_repo.low_rated_assistant_messages(session, 5)

    low_rated_questions = []
    for m in raw_low_rated:
        agency_names = []
        for ag_id in clean_agency_ids(m.agency_ids):
            ag = next((a for a in agencies if str(a["id"]) == ag_id), None)
            if ag:
                agency_names.append(ag["short_name"])

        content = "ไม่ทราบคำถาม"
        if m.parent_id:
            parent_msg = await session.get(Message, m.parent_id)
            content = parent_msg.content if parent_msg else "ไม่ทราบคำถาม"

        low_rated_questions.append({
            "content": content,
            "feedback_text": m.feedback_text,
            "agency": ", ".join(agency_names) if agency_names else "-",
            "created_at": m.created_at.isoformat() if m.created_at else "",
        })

    total_ratings, up_count, down_count, satisfaction_rate = scalar_stats([totals])
    return FeedbackStats(
        total_ratings=total_ratings,
        up_count=up_count,
        down_count=down_count,
        satisfaction_rate=satisfaction_rate,
        daily_trend=daily_trend,
        low_rated_questions=low_rated_questions,
        agency_breakdown=agency_breakdown,
    )
