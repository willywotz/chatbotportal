"""
FastMCP Server — AI Chatbot Portal
Exposes agency data as MCP resources so LLM clients (e.g. Claude) can
discover which government agencies are available and how to reach them.

Registered resources
--------------------
  agencies://list → list_agency()   All active agencies (summary)

Registered tools
----------------
    list_agency → list_agency()   All active agencies (summary)
"""

import json
from datetime import datetime

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext
from opentelemetry import trace
from starlette.datastructures import URLPath

from app.auth.security import hash_api_key
from app.config import settings
from app.models.agency import Agency
from app.models.user import User, UserAPIKey
from app.utils import generate_uuid, now

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

        user = await ctx.fastmcp_context.get_state("user_id") or None
        conversation_id = await ctx.fastmcp_context.get_state("conversation_id") or None

        if not user:
            token = get_http_request().headers.get("Authorization", "Bearer anonymous").split(" ")[-1]
            api_key = await UserAPIKey.filter(key_hash=hash_api_key(token)).first()
            if api_key and api_key.is_usable():
                api_key.last_used_at = now()
                await api_key.save(update_fields=["last_used_at"])
                user = await User.filter(id=api_key.user_id, is_active=True).first()
            if user: await ctx.fastmcp_context.set_state("user_id", user.id)
            if user: await ctx.fastmcp_context.set_state("user_is_admin", user.is_admin)

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
    TRACE_URL_PROBE to check whether OneChat preserves query strings."""
    url = f"{_external_scheme(request)}://{request.headers.get('X-Forwarded-Host')}/agent-proxy/{agency_id}"
    if settings.TRACE_URL_PROBE:
        url += f"?{settings.TRACE_URL_PROBE}"
    return url

@mcp.resource("agencies://list")
async def list_agency_resource(ctx: Context = CurrentContext()) -> str:
    """
    Return a JSON array of all *active* government agencies.
    """
    return json.dumps(await _fetch_agencies(ctx), default=_serialize, ensure_ascii=False, indent=2)

@mcp.tool("list_agency", description="Return a JSON array of all active government agencies.")
async def list_agency_tool(ctx: Context = CurrentContext()) -> dict:
    """
    Tool wrapper for list_agency_resource, which returns a JSON string.
    """

    agencies = await _fetch_agencies(ctx)

    return {"agencies": agencies, "total": len(agencies)}

async def _fetch_agencies(ctx: Context) -> dict:
    """
    Return a JSON array of all *active* government agencies.

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

    resolved_user_id = str(await ctx.get_state("user_id") or generate_uuid())
    resolved_conversation_id = str(await ctx.get_state("conversation_id") or generate_uuid())

    for index, agency in enumerate(agencies):
        if agency["api_headers"] is None:
            agencies[index]["api_headers"] = []

        for j, header in enumerate(agency["api_headers"]):
            if header.get("name").lower() == "authorization" and not user_is_admin:
                # agencies[index]["api_headers"][j]["value"] = "REDACTED"
                del agencies[index]["api_headers"][j]

        if agency["connection_type"] == "API":
            agency["endpoint_url"] = _agent_proxy_endpoint(request, agency["id"])

        for k, v in agency["expected_payload"].items():
            if isinstance(v, str) and "__user_id__" in v:
                agency["expected_payload"][k] = v.replace("__user_id__", resolved_user_id)
            if isinstance(v, str) and "__conversation_id__" in v:
                agency["expected_payload"][k] = v.replace("__conversation_id__", resolved_conversation_id)

    return agencies

from starlette.requests import Request
from starlette.responses import JSONResponse

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "mcp-server"})
