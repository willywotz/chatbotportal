"""
Feedback stats route — port of the Supabase `feedback-stats` edge function.

Endpoint
--------
  GET  /feedback/stats
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from app.auth.dependencies import get_current_user, require_admin
from app.models.user import User
from tortoise.functions import Count, Sum
from tortoise.expressions import Case, When, RawSQL, F
from tortoise.transactions import in_transaction

from app.config import settings
from app.models.conversation import Conversation, Message
from app.schemas.conversation import FeedbackStats
from app.models.agency import Agency
from app.utils import clean_agency_ids, now

router = APIRouter(prefix="/feedback", tags=["Feedback"])


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


@router.get("/agencies/{agency_id}/low-rated", summary="Down-rated answers for an agency (admin)")
async def get_agency_low_rated(agency_id: str, _: User = Depends(require_admin)):
    agency = await Agency.get_or_none(id=agency_id)
    if agency is None:
        raise HTTPException(status_code=404, detail="Agency not found")
    return await agency_low_rated(agency_id)


def _scalar_stats(message_state: list[dict]) -> tuple[int, int, int, int]:
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


@router.get("/stats", response_model=FeedbackStats, summary="Get feedback and satisfaction metrics")
async def feedback_stats(_user: User = Depends(get_current_user)) -> FeedbackStats:
    # Authorization is enforced by the global role allowlist: admin passes it;
    # a plain `user` is blocked upstream.

    # All rated messages, newest first
    # rated_messages = await (
    #     Message.filter(role="user", rating__not_isnull=True)
    #     .order_by("-created_at")
    #     .values("id", "rating", "feedback_text", "content", "created_at", "conversation_id")
    # )

    # up_count = sum(1 for m in rated_messages if m["rating"] == "up")
    # down_count = sum(1 for m in rated_messages if m["rating"] == "down")
    # total_ratings = up_count + down_count
    # satisfaction_rate = round((up_count / total_ratings) * 100) if total_ratings > 0 else 0

    # -------------------------------------------------------------------
    # Daily trend — last 14 days
    # -------------------------------------------------------------------
    # daily_map: dict[str, dict] = {}
    # for i in range(13, -1, -1):
    #     key = (now() - timedelta(days=i)).strftime("%m-%d")
    #     daily_map[key] = {"up": 0, "down": 0}

    # for m in rated_messages:
    #     if m["created_at"]:
    #         day_key = m["created_at"].strftime("%m-%d")
    #         if day_key in daily_map:
    #             if m["rating"] == "up":
    #                 daily_map[day_key]["up"] += 1
    #             elif m["rating"] == "down":
    #                 daily_map[day_key]["down"] += 1

    # daily_trend = [
    #     {
    #         "date": k,
    #         "up": v["up"],
    #         "down": v["down"],
    #         "rate": round((v["up"] / (v["up"] + v["down"])) * 100) if (v["up"] + v["down"]) > 0 else 0,
    #     }
    #     for k, v in daily_map.items()
    # ]

    # -------------------------------------------------------------------
    # Low-rated questions (last 10 down-rated assistant messages)
    # -------------------------------------------------------------------
    # down_rated = [m for m in rated_messages if m["rating"] == "down"][:10]
    # low_rated_questions = []

    # for dr in down_rated:
    #     # Get most recent user message from same conversation
    #     user_msg = await (
    #         Message.filter(conversation_id=dr["conversation_id"], role="user")
    #         .order_by("-created_at")
    #         .first()
    #     )
    #     conv = await Conversation.filter(id=dr["conversation_id"]).first()

    #     low_rated_questions.append({
    #         "content": user_msg.content if user_msg else "ไม่ทราบคำถาม",
    #         "feedback_text": dr.get("feedback_text"),
    #         "agency": ", ".join(conv.agencies) if conv and conv.agencies else "-",
    #         "created_at": dr["created_at"].isoformat() if dr.get("created_at") else "",
    #     })

    # -------------------------------------------------------------------
    # Agency breakdown
    # -------------------------------------------------------------------
    # agency_map: dict[str, dict] = {}
    # conv_ids = list({m["conversation_id"] for m in rated_messages})

    # if conv_ids:
    #     convs = await Conversation.filter(id__in=conv_ids).values("id", "agencies")
    #     conv_agency_map = {str(c["id"]): c["agencies"] or [] for c in convs}

    #     for m in rated_messages:
    #         conv_id = str(m["conversation_id"])
    #         for ag in conv_agency_map.get(conv_id, []):
    #             if ag not in agency_map:
    #                 agency_map[ag] = {"up": 0, "down": 0}
    #             if m["rating"] == "up":
    #                 agency_map[ag]["up"] += 1
    #             else:
    #                 agency_map[ag]["down"] += 1

    # agency_breakdown = sorted(
    #     [
    #         {
    #             "agency": ag,
    #             "up": v["up"],
    #             "down": v["down"],
    #             "rate": round((v["up"] / (v["up"] + v["down"])) * 100) if (v["up"] + v["down"]) > 0 else 0,
    #         }
    #         for ag, v in agency_map.items()
    #     ],
    #     key=lambda x: x["up"] + x["down"],
    #     reverse=True,
    # )

    # agency_breakdown = [
    #     {
    #         "agency": a["name"],
    #         "up": a["rating_up"],
    #         "down": a["rating_down"],
    #         "rate": round((a["rating_up"] / (a["rating_up"] + a["rating_down"])) * 100)
    #             if (a["rating_up"] + a["rating_down"]) > 0 else 0
    #     }
    #     for a in await Agency.all().values("name", "rating_up", "rating_down")
    # ]

    # return FeedbackStats(
    #     total_ratings=total_ratings,
    #     up_count=up_count,
    #     down_count=down_count,
    #     satisfaction_rate=satisfaction_rate,
    #     daily_trend=daily_trend,
    #     low_rated_questions=low_rated_questions,
    #     agency_breakdown=agency_breakdown,
    # )
    
    # print(Message \
    #     .annotate(
    #         rating_total=Count("rating"),
    #         rating_up=Sum(Case(When(rating="up", then=1), default=0)),
    #         rating_down=Sum(Case(When(rating="down", then=1), default=0))
    #     ) \
    #     .filter(rating__isnull=False) \
    #     .values("rating_total", "rating_up", "rating_down").sql(), flush=True)

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

        rawLowRatedQuestions = await Message \
            .filter(role="assistant", rating="down") \
            .order_by("-created_at") \
            .limit(5) \
            .values("feedback_text", "agency_ids", "created_at", "parent_id")
        
        low_rated_questions = []

        for index, entry in enumerate(rawLowRatedQuestions):        
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

        total_ratings, up_count, down_count, satisfaction_rate = _scalar_stats(message_state)
        return FeedbackStats(
            total_ratings=total_ratings,
            up_count=up_count,
            down_count=down_count,
            satisfaction_rate=satisfaction_rate,
            daily_trend=daily_trend,
            low_rated_questions=low_rated_questions,
            agency_breakdown=agency_breakdown,
        )
