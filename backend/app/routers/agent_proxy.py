"""Agent-proxy route: an external OneChat callback that this backend forwards
to the agency's real endpoint. Thin — all logic is in app/services/agent_proxy.
"""
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services import agent_proxy as agent_proxy_service

router = APIRouter(prefix="/agent-proxy", tags=["Agent Proxy"])

_HOP_BY_HOP = {"content-length", "content-encoding", "transfer-encoding", "connection"}


@router.api_route("/{agency_id}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def agent_proxy(agency_id: str, request: Request) -> StreamingResponse:
    body = await request.body()
    status_code, headers, stream = await agent_proxy_service.proxy(
        agency_id=agency_id,
        method=request.method,
        headers=dict(request.headers),
        body=body,
    )
    safe = {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}
    return StreamingResponse(stream, status_code=status_code, headers=safe)
