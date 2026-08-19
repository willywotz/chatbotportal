"""FastMCP server exposing Thai government agency data as the `list_agency` tool."""

import json

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext
from opentelemetry import trace
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.auth.keycloak import InvalidToken, verify_token
from app.config import settings
from app.models.agency import Agency
from app.trace_util import with_trace_query
from app.utils import generate_uuid

mcp = FastMCP(
    name="AI Chatbot Portal",
    instructions=(
        "Directory of Thai government agencies reachable through the AI Chatbot Portal.\n"
        "Call `list_agency` to get every active agency, then answer only from that data — "
        "never invent an agency, endpoint, or field.\n"
        "Each agency gives: id, name, description, connection_type (MCP | API | A2A), "
        "data_scope, endpoint_url, expected_payload."
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

def _external_scheme(request) -> str:
    # Behind a Cloudflare tunnel every hop speaks http; only cf-visitor
    # (`{"scheme":"https"}`) preserves the browser scheme. Fall back to
    # X-Forwarded-Proto, then the raw connection scheme.
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
    # The trace context rides in the query string so it survives OneChat's
    # header-dropping callback; TRACE_URL_PROBE is an optional debug marker.
    url = f"{_external_scheme(request)}://{request.headers.get('X-Forwarded-Host')}/api/v1/agent-proxy/{agency_id}"
    if settings.TRACE_URL_PROBE:
        url += ("&" if "?" in url else "?") + settings.TRACE_URL_PROBE
    return with_trace_query(url)

@mcp.tool("list_agency", description="Return a JSON array of all active government agencies.")
async def list_agency_tool(ctx: Context = CurrentContext()) -> dict:
    agencies = await _fetch_agencies(ctx)
    return {"agencies": agencies, "total": len(agencies)}

async def _fetch_agencies(ctx: Context) -> list[dict]:
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
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok\n")
