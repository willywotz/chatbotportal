import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import require_admin
from app.models.user import User
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
    status: str   # "done" | "error"
    time: int     # milliseconds


class AgentCardInfo(BaseModel):
    name: str
    skills: list[str] = []
    capabilities: dict[str, Any] = {}


class TestConnectionResponse(BaseModel):
    success: bool
    protocol: str          # "REST API" | "MCP" | "A2A" | "UNKNOWN"
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
async def update_agency_status(agency_id: uuid.UUID, body: StatusUpdateRequest, user: User = Depends(require_admin)):
    agency = await agency_service.get_agency_or_404(agency_id)
    old_status = await transition_status(agency, body.status)
    await record_audit(user, "agency.status_change", object_type="agency", object_id=agency.id, detail={"from": old_status, "to": body.status})
    return await _with_health(agency)


@router.post("/{agency_id}/conformance", summary="Run the conformance battery (admin)")
async def run_agency_conformance(agency_id: str, _: User = Depends(require_admin)):
    agency = await agency_service.get_agency_or_404(agency_id)
    from app.services.conformance import run_conformance
    return await run_conformance(agency)


@router.get("/{agency_id}/health/history", response_model=HealthHistoryResponse, summary="Agency health history")
async def agency_health_history(agency_id: uuid.UUID, window: str = "24h"):
    agency = await agency_service.get_agency_or_404(agency_id)
    buckets = await health_history(agency_id, window, agency.stats_reset_at)
    return HealthHistoryResponse(data=[HealthHistoryBucket(**b) for b in buckets])


@router.get(
    "/{agency_id}/test",
    response_model=TestConnectionResponse,
    summary="Test agency connection and record a connection log",
)
async def test_connection_endpoint(agency_id: uuid.UUID, _: User = Depends(require_admin)) -> TestConnectionResponse:
    agency = await agency_service.get_agency_or_404(agency_id)
    raw = await agency_service.run_connection_test(agency)

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
