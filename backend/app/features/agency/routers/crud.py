"""CRUD endpoints: list, get, create, replace, partial-update, delete, increment-calls.

list_agencies and create_agency are exported as bare functions; the package
__init__.py registers them directly on the prefix router to avoid the FastAPI
empty-path constraint with include_router.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.dependencies import require_scope
from app.core.security.principal import Principal
from app.core.db import get_db
from app.features.agency.routers._utils import _with_health
from app.features.agency.schemas.agency import (
    AgencyCreate,
    AgencyListResponse,
    AgencyResponse,
    AgencyUpdate,
)
from app.features.agency.services import agency as agency_service
from app.core.audit import record_audit

router = APIRouter()


# list_agencies and create_agency are registered by __init__.py directly
# on the /agencies prefix router to avoid FastAPI's empty-path constraint.

async def list_agencies(
    status_filter: Literal["active", "draft", "maintenance", "disabled", "all"] = Query(
        "all", alias="status", description="Filter by agency status"
    ),
    connection_type: str | None = Query(None, description="Filter by connection type: MCP, API, A2A"),
    search: str | None = Query(None, description="Search by name or short_name"),
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["agency:list"]),
):
    agencies, total = await agency_service.list_agencies(
        session, status_filter=status_filter, connection_type=connection_type, search=search
    )
    data = [await _with_health(session, a) for a in agencies]
    return AgencyListResponse(data=data, total=total)


async def create_agency(
    body: AgencyCreate,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["agency:write"]),
):
    agency = await agency_service.create_agency(session, body)
    return await _with_health(session, agency)


@router.get(
    "/{agency_id}",
    response_model=AgencyResponse,
    summary="Get agency by ID",
    dependencies=[Security(require_scope, scopes=["agency:read"])],
)
async def get_agency(agency_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    agency = await agency_service.get_agency_or_404(session, agency_id)
    return await _with_health(session, agency)


@router.put("/{agency_id}", response_model=AgencyResponse, summary="Replace agency")
async def replace_agency(
    agency_id: uuid.UUID,
    body: AgencyCreate,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["agency:write"]),
):
    agency = await agency_service.get_agency_or_404(session, agency_id)
    agency = await agency_service.replace_agency(session, agency, body)
    await record_audit(session, user, "agency.update", object_type="agency", object_id=agency.id)
    return await _with_health(session, agency)


@router.patch("/{agency_id}", response_model=AgencyResponse, summary="Partial update agency")
async def update_agency(
    agency_id: uuid.UUID,
    body: AgencyUpdate,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["agency:write"]),
):
    agency = await agency_service.get_agency_or_404(session, agency_id)
    agency = await agency_service.update_agency(session, agency, body)
    await record_audit(session, user, "agency.update", object_type="agency", object_id=agency.id)
    return await _with_health(session, agency)


@router.delete("/{agency_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete agency")
async def delete_agency(
    agency_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["agency:write"]),
):
    agency = await agency_service.get_agency_or_404(session, agency_id)
    await agency_service.delete_agency(session, agency)
    await record_audit(session, user, "agency.delete", object_type="agency", object_id=agency_id)


@router.post(
    "/{agency_id}/increment-calls",
    response_model=AgencyResponse,
    summary="Increment agency call counter",
)
async def increment_calls(
    agency_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["agency:write"]),
):
    agency = await agency_service.get_agency_or_404(session, agency_id)
    agency = await agency_service.increment_calls(session, agency)
    return AgencyResponse.model_validate(agency)
