import json as _json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.errors import ApiError, ErrorCode
from app.core.probe import probe_reachability
from app.features.agency.models.agency import Agency
from app.features.agency.repositories import agency as agency_repo
from app.features.agency.schemas.agency import AgencyCreate, AgencyUpdate
from app.features.monitoring.repositories import check_state as cs_repo
from app.features.monitoring.services import monitor
from app.core.log_sanitize import sanitize_body
from app.core.utils import now

logger = logging.getLogger(__name__)

# Fields that identify *how* an agency is reached. Changing any of these on a
# live agency invalidates its conformance battery, so it must be re-vetted.
_CONNECTION_IDENTITY_FIELDS = frozenset(
    {"connection_type", "endpoint_url", "api_headers", "expected_payload", "mcp_tool_name"}
)


async def get_agency_or_404(session: AsyncSession, agency_id: UUID) -> Agency:
    agency = await agency_repo.by_id(session, agency_id)
    if agency is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Agency not found", status=404)
    return agency


async def list_agencies(
    session: AsyncSession, *, status_filter: str, connection_type: str | None, search: str | None
) -> tuple[list[Agency], int]:
    return await agency_repo.list_and_count(
        session, status=status_filter, connection_type=connection_type, search_text=search)


def _flatten_agency_payload(body: AgencyCreate) -> dict:
    """Flatten a full agency payload's nested sub-schemas into plain dicts."""
    data = body.model_dump()
    data["api_endpoints"] = [e.model_dump() for e in body.api_endpoints]
    data["response_schema"] = [f.model_dump() for f in body.response_schema]
    data["api_headers"] = [h.model_dump() for h in body.api_headers] if body.api_headers else []
    return data


def _apply(agency: Agency, data: dict) -> None:
    for field, value in data.items():
        setattr(agency, field, value)


async def create_agency(session: AsyncSession, body: AgencyCreate) -> Agency:
    return await agency_repo.create(session, **_flatten_agency_payload(body))


async def replace_agency(session: AsyncSession, agency: Agency, body: AgencyCreate) -> Agency:
    _apply(agency, _flatten_agency_payload(body))
    await agency_repo.save(session, agency)
    return agency


async def update_agency(session: AsyncSession, agency: Agency, body: AgencyUpdate) -> Agency:
    update_data = body.model_dump(exclude_unset=True)

    for field in ("api_endpoints", "response_schema", "api_headers"):
        if update_data.get(field) is not None:
            update_data[field] = [e.model_dump() if hasattr(e, "model_dump") else e for e in update_data[field]]

    connection_changed = any(
        field in update_data and update_data[field] != getattr(agency, field)
        for field in _CONNECTION_IDENTITY_FIELDS
    )
    if connection_changed and agency.status in ("active", "maintenance"):
        update_data["status"] = "draft"
        update_data["conformance_report"] = None

    _apply(agency, update_data)
    await agency_repo.save(session, agency)
    return agency


async def delete_agency(session: AsyncSession, agency: Agency) -> None:
    await agency_repo.delete(session, agency)


async def increment_calls(session: AsyncSession, agency: Agency) -> Agency:
    return await agency_repo.increment_calls(session, agency)


async def run_connection_test(session: AsyncSession, agency: Agency) -> dict[str, Any]:
    """Probe `agency`, persist the reset baseline, and record the result into
    the uptime monitor (check-state, buckets, incident), auto-recovering a
    rule-set maintenance agency on success. Writes no `ConnectionLog` row."""
    agency.stats_reset_at = now()
    raw = await probe_reachability(agency.connection_type, agency.endpoint_url)
    await agency_repo.save(session, agency, update_fields=["stats_reset_at", "updated_at"])

    await cs_repo.ensure_states(session, settings.DEFAULT_CHECK_INTERVAL_SECONDS)
    state = await cs_repo.get_for_update(session, agency.id)
    ok = bool(raw.get("success"))
    latency_ms = int(str(raw.get("latency", "0")).replace("ms", "") or 0)
    status_code = raw.get("statusCode")
    detail = sanitize_body(raw.get("error") or (f"HTTP {status_code}" if status_code else raw["protocol"]))
    await monitor.record_result(session, state, agency, ok=ok, latency_ms=latency_ms, detail=detail, ts=now())
    return raw


async def parse_spec(spec_text: str) -> dict[str, Any]:
    """Call LLM to parse an OpenAPI spec and extract structured metadata.

    Raises ValueError on LLM API error or missing tool call arguments.
    """
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "You are an API specification parser. Extract structured information from OpenAPI/Swagger specs including response schemas.",
            },
            {
                "role": "user",
                "content": f"Parse this API specification and extract the details including response field schemas:\n\n{spec_text[:settings.SPEC_TEXT_MAX_CHARS]}",
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "extract_api_spec",
                    "description": "Extract structured API specification details including response schemas",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "auth_method": {
                                "type": "string",
                                "enum": ["api_key", "oauth2", "basic_auth", "none"],
                                "description": "Authentication method used by the API",
                            },
                            "auth_header": {
                                "type": "string",
                                "description": "Authentication header name, e.g. X-API-Key, Authorization",
                            },
                            "base_path": {
                                "type": "string",
                                "description": "Base path prefix for all endpoints, e.g. /api/v1",
                            },
                            "request_format": {
                                "type": "string",
                                "enum": ["json", "xml"],
                                "description": "Default request/response format",
                            },
                            "endpoints": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]},
                                        "path": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["method", "path", "description"],
                                    "additionalProperties": False,
                                },
                            },
                            "response_schema": {
                                "type": "array",
                                "description": "Common response fields found across endpoint responses",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "field": {"type": "string", "description": "Field name or dot-notation path e.g. data.items[].name"},
                                        "type": {"type": "string", "description": "Data type: string, number, boolean, array, object, date"},
                                        "description": {"type": "string", "description": "What this field contains"},
                                        "example": {"type": "string", "description": "Example value"},
                                    },
                                    "required": ["field", "type", "description"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["auth_method", "auth_header", "base_path", "request_format", "endpoints", "response_schema"],
                        "additionalProperties": False,
                    },
                },
            },
        ],
        "tool_choice": {"type": "function", "function": {"name": "extract_api_spec"}},
    }

    from app.features.llm.services import Purpose, chat
    async with AsyncSessionLocal() as session, session.begin():
        res = await chat(session, purpose=Purpose.PARSE_SPEC, messages=payload["messages"],
                         tools=payload["tools"], tool_choice=payload["tool_choice"])
    tool_call = (res.tool_calls or [{}])[0]
    args_raw = tool_call.get("function", {}).get("arguments")
    if not args_raw:
        raise ValueError("Failed to parse specification")
    return _json.loads(args_raw)
