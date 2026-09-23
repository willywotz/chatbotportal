import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.analytics.repositories import analytics as analytics_repo
from app.core.utils import now

logger = logging.getLogger(__name__)

_DAY_NAMES = ["อาทิตย์", "จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์"]


async def get_dashboard_stats(session: AsyncSession) -> dict:
    stats = {
        "totalQuestions": 0,
        "totalQuestionsTrend": 0.0,
        "todayQuestions": 0,
        "todayQuestionsTrend": 0.0,
        "avgResponseTime": 0.0,
        "avgResponseTimeTrend": 0.0,
        "satisfactionRate": 0.0,
        "satisfactionRateTrend": 0.0,
    }

    stats["totalQuestions"] = await analytics_repo.message_role_count(session, "user")

    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now().replace(hour=23, minute=59, second=59, microsecond=999999)
    stats["todayQuestions"] = await analytics_repo.message_role_count(
        session, "user", since=today_start, until=today_end)

    avg_response_time = await analytics_repo.message_avg_response_time_ms(session)
    stats["avgResponseTime"] = float(round(avg_response_time or 0, 2))

    rate = await analytics_repo.message_satisfaction_rate(session)
    stats["satisfactionRate"] = float(round(rate or 0, 2))

    agency_usage = [
        {"name": a["name"], "value": a["total_calls"], "fill": a["color"]}
        for a in await analytics_repo.list_agencies_usage(session)
    ]

    dow_map = await analytics_repo.message_weekly_dow_counts(session)
    weekly_trend = [{"day": _DAY_NAMES[i], "questions": dow_map.get(i, 0)} for i in range(len(_DAY_NAMES))]

    categories = await analytics_repo.message_category_counts(session)
    category_data = sorted(
        [{"category": row["category"], "count": row["cnt"]} for row in categories],
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "stats": stats,
        "agencyUsage": agency_usage,
        "weeklyTrend": weekly_trend,
        "categoryData": category_data,
    }
