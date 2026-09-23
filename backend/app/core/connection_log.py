from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ApiError, ErrorCode
from app.core.models.connection_log import ConnectionLog
from app.features.agency.repositories import agency as agency_repo
from app.features.analytics.repositories import analytics as analytics_repo
from app.core.repositories import connection_log as connection_log_repo
from app.core.utils import now


async def get_stats(session: AsyncSession, include_test: bool) -> dict:
    since = now() - timedelta(days=settings.AVG_LATENCY_WINDOW_DAYS)
    return await analytics_repo.connection_log_stats(session, since=since, include_test=include_test)


async def list_logs(
    session: AsyncSession,
    *,
    search: str | None,
    agency_id: str | None,
    status_filter: str | None,
    connection_type: str | None,
    include_test: bool,
    page: int,
    limit: int,
) -> tuple[list[ConnectionLog], dict]:
    filters = [] if include_test else [ConnectionLog.action != "test"]
    if search:
        filters.append(ConnectionLog.detail.ilike(f"%{search}%"))

    agency_uuid = None
    if agency_id:
        try:
            agency_uuid = uuid.UUID(agency_id)
        except ValueError:
            raise ApiError(ErrorCode.INVALID_REQUEST, "Invalid agency ID", status=400)
        if await agency_repo.by_id(session, agency_uuid) is None:
            raise ApiError(ErrorCode.INVALID_REQUEST, "Invalid agency ID", status=400)
        filters.append(ConnectionLog.agency_id == agency_uuid)

    if status_filter:
        filters.append(ConnectionLog.status == status_filter)
    if connection_type:
        filters.append(ConnectionLog.connection_type == connection_type)

    stmt = select(ConnectionLog).where(*filters).order_by(ConnectionLog.created_at.desc())
    if page and limit:
        stmt = stmt.offset((page - 1) * limit).limit(limit)
    logs = list((await session.execute(stmt)).scalars().all())

    since = now() - timedelta(days=settings.AVG_LATENCY_WINDOW_DAYS)
    stats = await analytics_repo.connection_log_stats(
        session, since=since, agency_id=agency_uuid, status=status_filter,
        connection_type=connection_type, search=search, include_test=include_test,
    )
    stats["total_items"] = stats["total_connections"]
    return logs, stats


async def get_log(session: AsyncSession, log_id: str) -> ConnectionLog:
    log = await connection_log_repo.get(session, log_id)
    if log is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Connection log not found", status=404)
    return log
