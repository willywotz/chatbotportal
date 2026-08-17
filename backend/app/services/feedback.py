"""
Business logic for the feedback dashboard: agency low-rated answers and the
overall satisfaction stats aggregate.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException, status
from tortoise.expressions import RawSQL
from tortoise.functions import Count
from tortoise.transactions import in_transaction

from app.config import settings
from app.models.agency import Agency
from app.models.conversation import Message
from app.schemas.conversation import FeedbackStats
from app.utils import clean_agency_ids, now


async def agency_low_rated(agency_id: str, limit: int = 50) -> list[dict]:
    """Recent down-rated assistant answers involving an agency.

    `agency_ids` is a JSON list; `__contains` on JSON is not portable to
    SQLite, so we fetch down-rated assistant messages then filter membership
    in Python. The `limit` caps the DB query BEFORE the Python membership
    filter, so the result may contain fewer than `limit` rows for this agency.
    That is acceptable for a "recent low-rated" view.
    """
    rows = (
        await Message.filter(role="assistant", rating="down")
        .order_by("-created_at").limit(limit)
    )
    out = [m for m in rows if agency_id in clean_agency_ids(m.agency_ids)]
    return [
        {"id": str(m.id), "content": m.content, "feedback_text": m.feedback_text,
         "created_at": str(m.created_at)}
        for m in out
    ]


async def agency_low_rated_or_404(agency_id: str, limit: int = 50) -> list[dict]:
    if not await Agency.filter(id=agency_id).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agency not found")
    return await agency_low_rated(agency_id, limit)


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


async def get_feedback_stats() -> FeedbackStats:
    async with in_transaction() as conn:
        await conn.execute_query(f"SET TIME ZONE '{settings.TIMEZONE}';")

        message_state = await Message \
            .annotate(
                total_rating=Count("rating"),
                rating_up=RawSQL('SUM(CASE WHEN rating = \'up\' THEN 1 ELSE 0 END)'),
                rating_down=RawSQL('SUM(CASE WHEN rating = \'down\' THEN 1 ELSE 0 END)'),
                rate=RawSQL('AVG(CASE WHEN rating = \'up\' THEN 1 ELSE 0 END) * 100')
            ) \
            .filter(rating__isnull=False) \
            .values("total_rating", "rating_up", "rating_down", "rate")

        daily_trend = await Message \
            .annotate(
                date=RawSQL("TO_CHAR(created_at, 'MM-DD')"),
                up=RawSQL('SUM(CASE WHEN rating = \'up\' THEN 1 ELSE 0 END)'),
                down=RawSQL('SUM(CASE WHEN rating = \'down\' THEN 1 ELSE 0 END)'),
                rate=RawSQL('0'),
            ) \
            .filter(rating__isnull=False, created_at__gte=now() - timedelta(days=settings.FEEDBACK_TREND_DAYS)) \
            .group_by("date") \
            .order_by("date") \
            .values("date", "up", "down", "rate")

        agency_breakdown = []

        agencies = await Agency.all().values("id", "short_name")

        for ag in agencies:
            stats = await Message \
                .annotate(
                    rating_up=RawSQL('SUM(CASE WHEN rating = \'up\' THEN 1 ELSE 0 END)'),
                    rating_down=RawSQL('SUM(CASE WHEN rating = \'down\' THEN 1 ELSE 0 END)'),
                ) \
                .filter(
                    rating__isnull=False,
                    agency_ids__contains=[str(ag["id"])],
                ) \
                .values("rating_up", "rating_down")

            rating_up = stats[0]["rating_up"] if stats and stats[0]["rating_up"] is not None else 0
            rating_down = stats[0]["rating_down"] if stats and stats[0]["rating_down"] is not None else 0

            agency_breakdown.append({
                "agency": ag["short_name"],
                "up": rating_up,
                "down": rating_down,
                "rate": 0,
            })

        raw_low_rated_questions = await Message \
            .filter(role="assistant", rating="down") \
            .order_by("-created_at") \
            .limit(5) \
            .values("feedback_text", "agency_ids", "created_at", "parent_id")

        low_rated_questions = []

        for entry in raw_low_rated_questions:
            agency_names = []
            for ag_id in clean_agency_ids(entry["agency_ids"]):
                ag = next((a for a in agencies if str(a["id"]) == ag_id), None)
                if ag:
                    agency_names.append(ag["short_name"])

            entry["agency"] = ", ".join(agency_names) if agency_names else "-"
            entry["created_at"] = entry["created_at"].isoformat() if entry.get("created_at") else ""

            if entry["parent_id"]:
                parent_msg = await Message.filter(id=entry["parent_id"]).first()
                entry["content"] = parent_msg.content if parent_msg else "ไม่ทราบคำถาม"

            low_rated_questions.append({
                "content": entry.get("content", "ไม่ทราบคำถาม"),
                "feedback_text": entry["feedback_text"],
                "agency": entry["agency"],
                "created_at": entry["created_at"],
            })

        total_ratings, up_count, down_count, satisfaction_rate = scalar_stats(message_state)
        return FeedbackStats(
            total_ratings=total_ratings,
            up_count=up_count,
            down_count=down_count,
            satisfaction_rate=satisfaction_rate,
            daily_trend=daily_trend,
            low_rated_questions=low_rated_questions,
            agency_breakdown=agency_breakdown,
        )
