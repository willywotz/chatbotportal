from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from tortoise.exceptions import DoesNotExist
from tortoise.functions import Avg

from app.config import settings
from app.models import Agency, ConnectionLog
from app.utils import now


def _base_queryset(include_test: bool):
    qs = ConnectionLog.all()
    return qs if include_test else qs.exclude(action="test")


async def _average_latency_ms(qs) -> int:
    cutoff = now() - timedelta(days=settings.AVG_LATENCY_WINDOW_DAYS)
    rows = await qs.filter(created_at__gte=cutoff).annotate(avg=Avg("latency_ms")).values("avg")
    return int(rows[0]["avg"] or 0) if rows else 0


async def _stats(qs) -> dict:
    return {
        "total_connections": await qs.count(),
        "successful_connections": await qs.filter(status="success").count(),
        "failed_connections": await qs.filter(status="error").count(),
        "average_latency_ms": await _average_latency_ms(qs),
    }


async def get_stats(include_test: bool) -> dict:
    return await _stats(_base_queryset(include_test))


async def list_logs(
    *,
    search: str | None,
    agency_id: str | None,
    status_filter: str | None,
    connection_type: str | None,
    include_test: bool,
    page: int,
    limit: int,
) -> tuple[list[ConnectionLog], dict]:
    qs = _base_queryset(include_test)
    if search:
        qs = qs.filter(detail__icontains=search)
    if agency_id:
        try:
            agency_uuid = uuid.UUID(agency_id)
            await Agency.get(id=agency_uuid)
            qs = qs.filter(agency_id=agency_uuid)
        except (ValueError, DoesNotExist):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid agency ID")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if connection_type:
        qs = qs.filter(connection_type=connection_type)

    qs_pagination = qs
    if page and limit:
        qs_pagination = qs.offset((page - 1) * limit).limit(limit)

    logs = await qs_pagination.order_by("-created_at")
    stats = await _stats(qs)
    stats["total_items"] = stats["total_connections"]
    return logs, stats


async def get_log(log_id: str) -> ConnectionLog:
    try:
        return await ConnectionLog.get(id=log_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection log not found")
