from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, require_admin
from app.models import ConnectionLog, User
from app.services import connection_log as connection_log_service

router = APIRouter(prefix="/connection-logs", tags=["Connection Logs"])


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


def _to_item(log: ConnectionLog) -> ConnectionLogItem:
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

    effective_limit = page_size if page_size is not None else limit
    logs, stats = await connection_log_service.list_logs(
        search=search,
        agency_id=agency_id,
        status_filter=status_filter,
        connection_type=connection_type,
        include_test=include_test,
        page=page,
        limit=effective_limit,
    )
    return ListConnectionLogResponse(
        search=search,
        page=page,
        page_size=effective_limit,
        items=[_to_item(log) for log in logs],
        **stats,
    )


@router.get("/items/{id}", summary="Get connection log detail", response_model=ConnectionLogItem)
async def get_connection_log_detail(id: str, _: User = Depends(require_admin)) -> ConnectionLogItem:
    log = await connection_log_service.get_log(id)
    return _to_item(log)


class ConnectionLogInfoResponse(BaseModel):
    total_connections: int
    successful_connections: int
    failed_connections: int
    average_latency_ms: int

@router.get("/information", summary="Get connection log info", response_model=ConnectionLogInfoResponse)
async def get_connection_log_info(
    include_test: bool = Query(False, description="Include action=test logs"),
    user: User = Depends(get_current_user),
) -> ConnectionLogInfoResponse:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    stats = await connection_log_service.get_stats(include_test)
    return ConnectionLogInfoResponse(**stats)
