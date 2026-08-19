"""
FastMCP Server — AI Chatbot Portal
Exposes agency data as MCP resources so LLM clients (e.g. Claude) can
discover which government agencies are available and how to reach them.

Registered resources
--------------------
  agencies://list → list_agency_resource()   All active agencies (JSON string)

Registered tools
----------------
  list_agency → list_agency_tool()   All active agencies (agencies + total)
"""

import json
from datetime import datetime

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext
from opentelemetry import trace
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth.keycloak import InvalidToken, verify_token
from app.config import settings
from app.models.agency import Agency
from app.trace_util import with_trace_query
from app.utils import generate_uuid

mcp = FastMCP(
    name="AI Chatbot Portal MCP",
    instructions=(
        "This server exposes Thai government agency data for the AI Chatbot Portal.\n\n"
        "Available tool:\n"
        "- list_agency: Returns a JSON object with an `agencies` array and `total` count. "
        "Each agency contains: id, name, description, connection_type "
        "(MCP | API | A2A), data_scope (list of data categories), "
        "endpoint_url, expected_payload.\n\n"
        "Always call list_agency before answering questions about available agencies. "
        "Never fabricate agency data."
    ),
)

class AuthMiddleware(Middleware):
    async def on_request(self, ctx: MiddlewareContext, call_next):
        if not await ctx.fastmcp_context.get_state("user_id"):
            token = get_http_request().headers.get("Authorization", "Bearer anonymous").split(" ")[-1]
            try:
                principal = verify_token(token)
            except InvalidToken:
                principal = None
            if principal:
                await ctx.fastmcp_context.set_state("user_id", principal.id)
                await ctx.fastmcp_context.set_state("user_is_admin", principal.is_admin)

        conversation_id = await ctx.fastmcp_context.get_state("conversation_id")
        if not conversation_id:
            conversation_id = str(generate_uuid())
            await ctx.fastmcp_context.set_state("conversation_id", conversation_id)

        trace.get_current_span().set_attribute("conversation_id", conversation_id)

        return await call_next(ctx)

mcp.add_middleware(AuthMiddleware())

def _serialize(value):
    """JSON-serialise datetime and UUID objects."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)

def _external_scheme(request) -> str:
    """Resolve the browser-facing scheme.

    Behind a Cloudflare tunnel the whole chain speaks HTTP, so request.url.scheme
    and X-Forwarded-Proto are both "http". Cloudflare preserves the real scheme in
    `cf-visitor` (`{"scheme":"https"}`); prefer it, then X-Forwarded-Proto, then the
    raw connection scheme.
    """
    cf_visitor = request.headers.get("cf-visitor")
    if cf_visitor:
        try:
            scheme = json.loads(cf_visitor).get("scheme")
        except (json.JSONDecodeError, AttributeError):
            scheme = None
        if scheme:
            return scheme
    return request.headers.get("X-Forwarded-Proto") or request.url.scheme

def _agent_proxy_endpoint(request, agency_id: str) -> str:
    """Build the agent-proxy URL OneChat calls back, optionally tagged with
    TRACE_URL_PROBE to check whether OneChat preserves query strings, and
    always tagged with the active W3C trace context so it survives OneChat's
    header-dropping callback."""
    url = f"{_external_scheme(request)}://{request.headers.get('X-Forwarded-Host')}/api/v1/agent-proxy/{agency_id}"
    if settings.TRACE_URL_PROBE:
        url += ("&" if "?" in url else "?") + settings.TRACE_URL_PROBE
    return with_trace_query(url)

@mcp.resource("agencies://list")
async def list_agency_resource(ctx: Context = CurrentContext()) -> str:
    """
    Return a JSON array of all *active* government agencies.
    """
    return json.dumps(await _fetch_agencies(ctx), default=_serialize, ensure_ascii=False, indent=2)

@mcp.tool("list_agency", description="Return a JSON array of all active government agencies.")
async def list_agency_tool(ctx: Context = CurrentContext()) -> dict:
    """
    Return active agencies as an object with an `agencies` list and a `total`
    count. The `agencies://list` resource returns the same data as a JSON string.
    """

    agencies = await _fetch_agencies(ctx)

    return {"agencies": agencies, "total": len(agencies)}

async def _fetch_agencies(ctx: Context) -> list[dict]:
    """
    Return a list of all *active* government agencies.

    Each item contains:
    - id
    - name
    - status
    - description
    - connection_type  (MCP | API | A2A)
    - data_scope       list of data categories this agency covers
    - endpoint_url     base URL of the agency's API
    - expected_payload example JSON payload for API calls
    """

    request = get_http_request()

    user_is_admin = await ctx.get_state("user_is_admin")

    agencies = await Agency.all().values(
        "id",
        "name",
        "status",
        "description",
        "connection_type",
        "data_scope",
        "endpoint_url",
        "expected_payload",
        "api_headers",
    )

    placeholders = {
        "__user_id__": str(await ctx.get_state("user_id") or generate_uuid()),
        "__conversation_id__": str(await ctx.get_state("conversation_id") or generate_uuid()),
    }

    for agency in agencies:
        headers = agency["api_headers"] or []
        if not user_is_admin:
            # Strip every credential so non-admin callers never see it (trust boundary).
            headers = [h for h in headers if h.get("name", "").lower() != "authorization"]
        agency["api_headers"] = headers

        if agency["connection_type"] == "API":
            agency["endpoint_url"] = _agent_proxy_endpoint(request, agency["id"])

        payload = agency["expected_payload"]
        for key, value in payload.items():
            if isinstance(value, str):
                for token, resolved in placeholders.items():
                    value = value.replace(token, resolved)
                payload[key] = value

    return agencies

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "mcp-server"})
