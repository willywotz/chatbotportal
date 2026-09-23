from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agency import Agency
from app.models.connection_log import ConnectionLog
from app.models.conversation import Conversation, Message
from app.models.llm_usage import LlmUsage

_USAGE_GROUP_COLUMNS = {"purpose": LlmUsage.purpose, "model": LlmUsage.model, "user": LlmUsage.user_id}
_USAGE_GROUP_NAMES = {"purpose": "purpose", "model": "model", "user": "user_id"}


async def _set_local_timezone(session: AsyncSession) -> None:
    """Scope date/time-bucketing SQL (EXTRACT, TO_CHAR, CURRENT_DATE) to app local time.

    SET LOCAL only lasts for the caller's transaction, so it never leaks onto a
    pooled connection reused by an unrelated request. Postgres SET does not accept
    a bind parameter ($1) — settings.TIMEZONE is trusted server config, not user
    input, so it is safe to inline.
    """
    await session.execute(text(f"SET LOCAL TIME ZONE '{settings.TIMEZONE}'"))


async def connection_log_avg_latency_by_agency(session: AsyncSession, since: datetime) -> dict[str, float]:
    """agency_id -> AVG(latency_ms) since `since`. Backs health.py's current/avg latency maps."""
    stmt = (
        select(ConnectionLog.agency_id, func.avg(ConnectionLog.latency_ms).label("avg_latency"))
        .where(ConnectionLog.created_at >= since)
        .group_by(ConnectionLog.agency_id)
    )
    rows = (await session.execute(stmt)).all()
    return {str(r.agency_id): r.avg_latency for r in rows}


async def connection_log_count_by_agency(session: AsyncSession, since: datetime) -> dict[str, int]:
    """agency_id -> COUNT(*) since `since`. Backs health.py's day_counts map."""
    stmt = (
        select(ConnectionLog.agency_id, func.count().label("total"))
        .where(ConnectionLog.created_at >= since)
        .group_by(ConnectionLog.agency_id)
    )
    rows = (await session.execute(stmt)).all()
    return {str(r.agency_id): r.total for r in rows}


async def connection_log_historical(session: AsyncSession, since: datetime) -> list[dict]:
    """Hourly (date, agency_id) latency+uptime buckets. Backs health.py's historical series."""
    await _set_local_timezone(session)
    date_expr = literal_column("TO_CHAR(created_at, 'MM-DD HH24:00')")
    stmt = (
        select(
            date_expr.label("date"),
            ConnectionLog.agency_id,
            func.avg(ConnectionLog.latency_ms).cast(Float).label("latency"),
            (func.avg(literal_column("CASE WHEN status >= 'success' THEN 1 ELSE 0 END")) * 100)
            .cast(Float).label("uptime"),
        )
        .where(ConnectionLog.created_at >= since)
        .group_by(date_expr, ConnectionLog.agency_id)
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def list_agencies_health_summary(session: AsyncSession) -> list[dict]:
    stmt = select(Agency.id, Agency.name, Agency.short_name, Agency.status, Agency.stats_reset_at)
    rows = (await session.execute(stmt)).all()
    return [{"id": r.id, "name": r.name, "short_name": r.short_name,
             "status": r.status.value if r.status else r.status, "stats_reset_at": r.stats_reset_at} for r in rows]


async def list_agencies_usage(session: AsyncSession) -> list[dict]:
    stmt = select(Agency.name, Agency.color, Agency.total_calls)
    rows = (await session.execute(stmt)).all()
    return [{"name": r.name, "color": r.color, "total_calls": r.total_calls} for r in rows]


async def list_agencies_basic(session: AsyncSession) -> list[dict]:
    stmt = select(Agency.id, Agency.name)
    rows = (await session.execute(stmt)).all()
    return [{"id": r.id, "name": r.name} for r in rows]


async def connection_log_stats(
    session: AsyncSession, *, since: datetime, agency_id=None, status: str | None = None,
    connection_type: str | None = None, search: str | None = None, include_test: bool = False,
) -> dict:
    filters = [] if include_test else [ConnectionLog.action != "test"]
    if agency_id is not None:
        filters.append(ConnectionLog.agency_id == agency_id)
    if status is not None:
        filters.append(ConnectionLog.status == status)
    if connection_type is not None:
        filters.append(ConnectionLog.connection_type == connection_type)
    if search:
        filters.append(ConnectionLog.detail.ilike(f"%{search}%"))

    total = await session.scalar(select(func.count()).select_from(ConnectionLog).where(*filters))
    successful = await session.scalar(
        select(func.count()).select_from(ConnectionLog).where(*filters, ConnectionLog.status == "success"))
    failed = await session.scalar(
        select(func.count()).select_from(ConnectionLog).where(*filters, ConnectionLog.status == "error"))
    avg_latency = await session.scalar(
        select(func.avg(ConnectionLog.latency_ms)).where(*filters, ConnectionLog.created_at >= since))
    return {
        "total_connections": total,
        "successful_connections": successful,
        "failed_connections": failed,
        "average_latency_ms": int(avg_latency or 0),
    }


async def message_role_count(session: AsyncSession, role: str, *, since: datetime | None = None,
                              until: datetime | None = None) -> int:
    stmt = select(func.count()).select_from(Message).where(Message.role == role)
    if since is not None:
        stmt = stmt.where(Message.created_at >= since)
    if until is not None:
        stmt = stmt.where(Message.created_at <= until)
    return await session.scalar(stmt)


async def conversation_count(session: AsyncSession, *, since: datetime | None = None,
                              until: datetime | None = None) -> int:
    stmt = select(func.count()).select_from(Conversation)
    if since is not None:
        stmt = stmt.where(Conversation.created_at >= since)
    if until is not None:
        stmt = stmt.where(Conversation.created_at <= until)
    return await session.scalar(stmt)


async def message_weekly_dow_counts(session: AsyncSession) -> dict[int, int]:
    """dow(0=Sunday..6=Saturday) -> COUNT(*) of user messages in the trailing 7 days."""
    await _set_local_timezone(session)
    rows = (await session.execute(text(
        """
        SELECT EXTRACT(DOW FROM created_at)::int AS dow, COUNT(*) AS questions
        FROM messages
        WHERE role = 'user' AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY dow
        """
    ))).mappings().all()
    return {row["dow"]: row["questions"] for row in rows}


async def message_avg_response_time_ms(session: AsyncSession) -> float | None:
    stmt = select((func.avg(Message.response_time) / 1000).cast(Float))
    return await session.scalar(stmt)


async def message_satisfaction_rate(session: AsyncSession) -> float | None:
    stmt = (
        select((func.avg(literal_column("CASE WHEN rating = 'up' THEN 1 ELSE 0 END")) * 100).cast(Float))
        .where(Message.rating.isnot(None))
    )
    return await session.scalar(stmt)


async def message_category_counts(session: AsyncSession) -> list[dict]:
    stmt = (
        select(Message.category, func.count(Message.id).label("cnt"))
        .where(Message.category.isnot(None))
        .group_by(Message.category)
    )
    rows = (await session.execute(stmt)).all()
    return [{"category": r.category, "cnt": r.cnt} for r in rows]


async def message_hourly_by_agency(session: AsyncSession, since: datetime) -> list[dict]:
    await _set_local_timezone(session)
    hour_expr = literal_column("extract(hour from created_at)")
    stmt = (
        select(Message.agency_ids, hour_expr.label("hour"), func.count(Message.id).label("cnt"))
        .where(Message.created_at >= since)
        .group_by(Message.agency_ids, hour_expr)
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def message_day_hour_matrix(session: AsyncSession, since: datetime) -> list[dict]:
    await _set_local_timezone(session)
    day_expr = literal_column("extract(dow from created_at)")
    hour_expr = literal_column("extract(hour from created_at)")
    stmt = (
        select(day_expr.label("day"), hour_expr.label("hour"), func.count(Message.id).label("cnt"))
        .where(Message.role == "user", Message.created_at >= since)
        .group_by(day_expr, hour_expr)
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def message_peak_day(session: AsyncSession, since: datetime) -> list[dict]:
    await _set_local_timezone(session)
    day_expr = literal_column("extract(dow from created_at)")
    stmt = (
        select(day_expr.label("day"), func.count(Message.id).label("cnt"))
        .where(Message.role == "user", Message.created_at >= since)
        .group_by(day_expr)
        .order_by(func.count(Message.id).desc())
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def message_peak_hour(session: AsyncSession, since: datetime) -> list[dict]:
    await _set_local_timezone(session)
    hour_expr = literal_column("extract(hour from created_at)")
    stmt = (
        select(hour_expr.label("hour"), func.count(Message.id).label("cnt"))
        .where(Message.role == "user", Message.created_at >= since)
        .group_by(hour_expr)
        .order_by(func.count(Message.id).desc())
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def message_monthly_trend(session: AsyncSession, since: datetime) -> list[dict]:
    await _set_local_timezone(session)
    month_expr = literal_column("TO_CHAR(created_at, 'YYYY-MM')")
    stmt = (
        select(
            month_expr.label("month"),
            func.sum(literal_column("CASE WHEN role = 'user' THEN 1 ELSE 0 END")).label("questions"),
            func.sum(literal_column("CASE WHEN rating = 'up' THEN 1 ELSE 0 END")).label("rating_up"),
            func.sum(literal_column("CASE WHEN rating = 'down' THEN 1 ELSE 0 END")).label("rating_down"),
        )
        .where(Message.created_at >= since)
        .group_by(month_expr)
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def llm_usage_summary(session: AsyncSession, group_by: str = "purpose",
                             date_from: datetime | None = None, date_to: datetime | None = None) -> list[dict]:
    column = _USAGE_GROUP_COLUMNS.get(group_by, LlmUsage.purpose)
    field_name = _USAGE_GROUP_NAMES.get(group_by, "purpose")
    stmt = (
        select(
            column.label(field_name),
            func.sum(LlmUsage.prompt_tokens).label("prompt"),
            func.sum(LlmUsage.completion_tokens).label("completion"),
            func.sum(LlmUsage.cost_usd).label("cost"),
        )
        .group_by(column)
    )
    if date_from is not None:
        stmt = stmt.where(LlmUsage.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(LlmUsage.created_at < date_to)
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]
