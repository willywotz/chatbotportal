import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Security
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_scope
from app.auth.principal import Principal
from app.db import get_db
from app.routers.agencies._utils import _with_health
from app.schemas.agency import (
    AgencyResponse,
    HealthHistoryBucket,
    HealthHistoryResponse,
    StatusUpdateRequest,
)
from app.services import agency as agency_service
from app.services.agency_health import health_history
from app.services.agency_lifecycle import transition_status
from app.services.audit import record_audit

router = APIRouter()


class TestStep(BaseModel):
    step: int
    label: str
    status: Literal["done", "error"]
    time_ms: int


class AgentCardInfo(BaseModel):
    name: str
    skills: list[str] = []
    capabilities: dict[str, Any] = {}


class TestConnectionResponse(BaseModel):
    success: bool
    protocol: Literal["REST API", "MCP", "A2A", "UNKNOWN"]
    version: str
    steps: list[TestStep]
    latency: str           # e.g. "142ms"

    # REST-only
    status_code: int | None = None
    status_text: str | None = None
    server: str | None = None
    content_type: str | None = None

    # MCP-only
    capabilities: list[str] | None = None
    server_info: dict[str, Any] | None = None

    # A2A-only
    agent_card: AgentCardInfo | None = None

    # Error (any protocol)
    error: str | None = None

    model_config = {"populate_by_name": True}


@router.patch("/{agency_id}/status", response_model=AgencyResponse, summary="Transition agency lifecycle status")
async def update_agency_status(
    agency_id: uuid.UUID,
    body: StatusUpdateRequest,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["agency:write"]),
):
    agency = await agency_service.get_agency_or_404(session, agency_id)
    old_status = await transition_status(session, agency, body.status)
    await record_audit(session, user, "agency.status_change", object_type="agency", object_id=agency.id, detail={"from": old_status, "to": body.status})
    return await _with_health(session, agency)


@router.post("/{agency_id}/conformance", summary="Run the conformance battery (admin)")
async def run_agency_conformance(
    agency_id: str,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["agency:write"]),
):
    agency = await agency_service.get_agency_or_404(session, agency_id)
    from app.services.conformance import run_conformance
    return await run_conformance(session, agency)


@router.get(
    "/{agency_id}/health/history",
    response_model=HealthHistoryResponse,
    summary="Agency health history",
    dependencies=[Security(require_scope, scopes=["agency:read"])],
)
async def agency_health_history(agency_id: uuid.UUID, window: str = "24h", session: AsyncSession = Depends(get_db)):
    agency = await agency_service.get_agency_or_404(session, agency_id)
    buckets = await health_history(session, agency_id, window, agency.stats_reset_at)
    return HealthHistoryResponse(data=[HealthHistoryBucket(**b) for b in buckets])


@router.get(
    "/{agency_id}/test",
    response_model=TestConnectionResponse,
    summary="Test agency connection and record a connection log",
)
async def test_connection_endpoint(
    agency_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["agency:write"]),
) -> TestConnectionResponse:
    agency = await agency_service.get_agency_or_404(session, agency_id)
    raw = await agency_service.run_connection_test(session, agency)

    agent_card_raw = raw.get("agentCard")
    return TestConnectionResponse(
        success=raw["success"],
        protocol=raw["protocol"],
        version=raw["version"],
        steps=[TestStep(**s) for s in raw.get("steps", [])],
        latency=raw["latency"],
        error=raw.get("error"),
        status_code=raw.get("statusCode"),
        status_text=raw.get("statusText"),
        server=raw.get("server"),
        content_type=raw.get("contentType"),
        capabilities=raw.get("capabilities"),
        server_info=raw.get("serverInfo"),
        agent_card=AgentCardInfo(**agent_card_raw) if agent_card_raw else None,
    )
