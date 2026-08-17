from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, require_admin
from app.models.user import User
from app.schemas.agency import McpDiscoverRequest, McpDiscoverResponse, McpToolInfo
from app.services.agency import parse_spec
from app.services.llm import LlmError
from app.services.mcp_discovery import discover_tools

router = APIRouter()


class ParseSpecRequest(BaseModel):
    spec_text: str


@router.post("/mcp/discover", response_model=McpDiscoverResponse, summary="Discover MCP tools at an endpoint")
async def mcp_discover(body: McpDiscoverRequest, _: User = Depends(require_admin)):
    if not body.endpoint_url.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="endpoint_url is required")
    try:
        tools = await discover_tools(body.endpoint_url)
    except Exception as exc:  # noqa: BLE001 — surface any MCP/connection failure to the client
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MCP discovery failed: {exc}")
    return McpDiscoverResponse(tools=[McpToolInfo(**t) for t in tools])


@router.post("/parse-spec", summary="Parse an OpenAPI spec via LLM and extract structured metadata")
async def parse_api_spec(body: ParseSpecRequest, _: User = Depends(get_current_user)):
    if not body.spec_text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="spec_text is required")

    try:
        parsed = await parse_spec(body.spec_text)
    except LlmError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LLM provider error: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return {"success": True, "data": parsed}
