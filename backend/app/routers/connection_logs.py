import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from tortoise.functions import Avg
from tortoise.exceptions import DoesNotExist
from app.models import Agency, ConnectionLog, User
from app.auth.dependencies import get_current_user, require_admin
from datetime import datetime, timedelta
from app.config import settings
from app.utils import now

router = APIRouter(prefix="/connection-logs", tags=["Connection Logs"])

# ---------------------------------------------------------------------------
# Connection logs
# ---------------------------------------------------------------------------

class ConnectionLogItem(BaseModel):
    id: str
    agency_id: str
    action: str
    connection_type: str
    status: str
    latency_ms: int
    detail: str
    created_at: str

class ListConnectionLogResponse(BaseModel):
    search: str | None = None
    page: int
    page_size: int

    items: list[ConnectionLogItem]
    total_items: int

    total_connections: int
    successful_connections: int
    failed_connections: int
    average_latency_ms: int

@router.get(
    "",
    
    response_model=ListConnectionLogResponse,
    summary="List connection logs",
)
async def list_connection_logs(
    search: str | None = Query(None, description="Search in detail"),
    agency_id: str | None = Query(None, description="Filter by agency ID"),
    status_filter: str | None = Query(None, alias="status", description="success | error"),
    connection_type: str | None = Query(None, description="MCP | API | A2A"),
    include_test: bool = Query(False, description="Include action=test logs"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    page_size: int | None = Query(None, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> ListConnectionLogResponse:

    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    qs = ConnectionLog.all()
    if not include_test:
        qs = qs.exclude(action="test")

    start = time.time()

    if search:
        qs = qs.filter(detail__icontains=search)

    if agency_id:
        try:
            agency_uuid = uuid.UUID(agency_id)
            await Agency.get(id=agency_uuid)  # Check if agency exists
            qs = qs.filter(agency_id=agency_uuid)
        except (ValueError, DoesNotExist):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid agency ID")

    if status_filter:
        qs = qs.filter(status=status_filter)
    if connection_type:
        qs = qs.filter(connection_type=connection_type)

    effective_limit = page_size if page_size is not None else limit

    qs_pagination = qs

    if page and effective_limit:
        offset = (page - 1) * effective_limit
        qs_pagination = qs.offset(offset).limit(effective_limit)

    logs = await qs_pagination.order_by("-created_at")

    total_connections = await qs.count()
    successful_connections = await qs.filter(status="success").count()
    failed_connections = await qs.filter(status="error").count()

    last_day_date = now() - timedelta(days=settings.AVG_LATENCY_WINDOW_DAYS)
    average_latency_ms = await qs.filter(created_at__gte=last_day_date).annotate(avg=Avg("latency_ms")).values("avg")
    average_latency_ms = int(average_latency_ms[0]["avg"] or 0) if average_latency_ms else 0

    return ListConnectionLogResponse(
        search=search,
        page=page,
        page_size=effective_limit,
        items=[
            ConnectionLogItem(
                id=str(log.id),
                agency_id=str(log.agency_id) if log.agency_id else "",
                action=log.action,
                connection_type=log.connection_type,
                status=log.status,
                latency_ms=log.latency_ms,
                detail=log.detail,
                created_at=log.created_at.isoformat(),
            )
            for log in logs
        ],
        total_items=await qs.count(),

        total_connections=total_connections,
        successful_connections=successful_connections,
        failed_connections=failed_connections,
        average_latency_ms=average_latency_ms,
    )

@router.get("/items/{id}", summary="Get connection log detail", response_model=ConnectionLogItem)
async def get_connection_log_detail(id: str, _: User = Depends(require_admin)) -> ConnectionLogItem:
    try:
        log = await ConnectionLog.get(id=id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection log not found")

    return ConnectionLogItem(
        id=str(log.id),
        agency_id=str(log.agency_id) if log.agency_id else "",
        action=log.action,
        connection_type=log.connection_type,
        status=log.status,
        latency_ms=log.latency_ms,
        detail=log.detail,
        created_at=log.created_at.isoformat(),
    )

class ConnectionLogInfoResponse(BaseModel):
    total_connections: int
    successful_connections: int
    failed_connections: int
    average_latency_ms: int

@router.get("/info", summary="Get connection log info", response_model=ConnectionLogInfoResponse)
async def get_connection_log_info(
    include_test: bool = Query(False, description="Include action=test logs"),
    user: User = Depends(get_current_user),
) -> ConnectionLogInfoResponse:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    qs = ConnectionLog.all()
    if not include_test:
        qs = qs.exclude(action="test")

    total_connections = await qs.count()
    successful_connections = await qs.filter(status="success").count()
    failed_connections = await qs.filter(status="error").count()

    last_day_date = now() - timedelta(days=settings.AVG_LATENCY_WINDOW_DAYS)
    average_latency_ms = await qs.filter(created_at__gte=last_day_date).annotate(avg=Avg("latency_ms")).values("avg")
    average_latency_ms = int(average_latency_ms[0]["avg"] or 0) if average_latency_ms else 0

    return ConnectionLogInfoResponse(
        total_connections=total_connections,
        successful_connections=successful_connections,
        failed_connections=failed_connections,
        average_latency_ms=average_latency_ms,
    )