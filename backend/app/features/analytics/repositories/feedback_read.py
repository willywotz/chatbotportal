from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.agency.models.agency import Agency
from app.features.chat.models.conversation import Message

_RATING_UP_SQL = "SUM(CASE WHEN rating = 'up' THEN 1 ELSE 0 END)"
_RATING_DOWN_SQL = "SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END)"


async def rating_totals(session: AsyncSession) -> dict:
    """Ungrouped rating aggregate over all rated messages. Backs feedback.py's scalar stats."""
    stmt = (
        select(
            func.count(Message.rating).label("total_rating"),
            literal_column(_RATING_UP_SQL).label("rating_up"),
            literal_column(_RATING_DOWN_SQL).label("rating_down"),
            (func.avg(literal_column("CASE WHEN rating = 'up' THEN 1 ELSE 0 END")) * 100)
            .cast(Float).label("rate"),
        )
        .where(Message.rating.isnot(None))
    )
    row = (await session.execute(stmt)).mappings().first()
    return dict(row)


async def rating_daily_trend(session: AsyncSession, since: datetime) -> list[dict]:
    # Postgres SET does not accept a bind parameter; settings.TIMEZONE is trusted config.
    await session.execute(text(f"SET LOCAL TIME ZONE '{settings.TIMEZONE}'"))
    date_expr = literal_column("TO_CHAR(created_at, 'MM-DD')")
    stmt = (
        select(date_expr.label("date"), literal_column(_RATING_UP_SQL).label("up"),
               literal_column(_RATING_DOWN_SQL).label("down"))
        .where(Message.rating.isnot(None), Message.created_at >= since)
        .group_by(date_expr)
        .order_by(date_expr)
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def agency_rating_counts(session: AsyncSession, agency_id) -> dict:
    stmt = (
        select(literal_column(_RATING_UP_SQL).label("rating_up"),
               literal_column(_RATING_DOWN_SQL).label("rating_down"))
        .where(Message.rating.isnot(None), Message.agency_ids.contains([str(agency_id)]))
    )
    row = (await session.execute(stmt)).mappings().first()
    return dict(row)


async def list_agencies_short_names(session: AsyncSession) -> list[dict]:
    rows = (await session.execute(select(Agency.id, Agency.short_name))).all()
    return [{"id": r.id, "short_name": r.short_name} for r in rows]


async def low_rated_assistant_messages(session: AsyncSession, limit: int) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.role == "assistant", Message.rating == "down")
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
