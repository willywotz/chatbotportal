import json as _json
import logging
import time
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from tortoise.exceptions import DoesNotExist
from tortoise.expressions import F

from app.config import settings
from app.models.agency import Agency
from app.models.connection_log import ConnectionLog
from app.schemas.agency import AgencyCreate, AgencyUpdate
from app.services.cache_flush import flush_similarity_cache
from app.services.log_sanitize import sanitize_body
from app.utils import now

logger = logging.getLogger(__name__)

_PROTOCOL = {"API": "REST API", "MCP": "MCP", "A2A": "A2A"}

# Fields that identify *how* an agency is reached. Changing any of these on a
# live agency invalidates its conformance battery, so it must be re-vetted.
_CONNECTION_IDENTITY_FIELDS = frozenset(
    {"connection_type", "endpoint_url", "api_headers", "expected_payload", "mcp_tool_name"}
)


async def get_agency_or_404(agency_id: UUID) -> Agency:
    try:
        return await Agency.get(id=agency_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agency not found")


async def list_agencies(
    *, status_filter: str, connection_type: str | None, search: str | None
) -> tuple[list[Agency], int]:
    qs = Agency.all()
    if status_filter != "all":
        qs = qs.filter(status=status_filter)
    if connection_type:
        qs = qs.filter(connection_type=connection_type.upper())
    if search:
        qs = qs.filter(name__icontains=search)
    return await qs, await qs.count()


def _full_payload(body: AgencyCreate) -> dict:
    """Flatten a full agency payload's nested sub-schemas into plain dicts."""
    data = body.model_dump()
    data["api_endpoints"] = [e.model_dump() for e in body.api_endpoints]
    data["response_schema"] = [f.model_dump() for f in body.response_schema]
    data["api_headers"] = [h.model_dump() for h in body.api_headers] if body.api_headers else []
    return data


async def create_agency(body: AgencyCreate) -> Agency:
    return await Agency.create(**_full_payload(body))


async def _flush_similarity_cache_best_effort() -> None:
    try:
        await flush_similarity_cache()
    except Exception:
        logger.exception("failed to flush similarity cache after agency update")


async def replace_agency(agency: Agency, body: AgencyCreate) -> Agency:
    await agency.update_from_dict(_full_payload(body)).save()
    await _flush_similarity_cache_best_effort()
    return agency


async def update_agency(agency: Agency, body: AgencyUpdate) -> Agency:
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

    await agency.update_from_dict(update_data).save()
    await _flush_similarity_cache_best_effort()
    return agency


async def delete_agency(agency: Agency) -> None:
    await agency.delete()


async def increment_calls(agency: Agency) -> Agency:
    """Atomically add one to total_calls, then refresh the readable value.

    A read-modify-write loses concurrent increments; the atomic SQL update
    matches the Go original and is race-safe.
    """
    await Agency.filter(id=agency.id).update(total_calls=F("total_calls") + 1)
    await agency.refresh_from_db(fields=["total_calls"])
    return agency


async def update_logo(agency: Agency, logo_url: str) -> Agency:
    agency.logo = logo_url
    await agency.save(update_fields=["logo", "updated_at"])
    return agency


def _failure(protocol: str, error: str, steps: list[dict] | None = None, latency_ms: int = 0) -> dict[str, Any]:
    return {"success": False, "protocol": protocol, "version": "-", "steps": steps or [],
            "latency": f"{latency_ms}ms", "error": error}


async def test_connection(connection_type: str, agency: Agency) -> dict[str, Any]:
    """Reachability probe: HEAD with a GET fallback.

    Any HTTP response — including 4xx/5xx — means the endpoint is reachable and
    counts as success. Only a transport failure (refused, DNS, timeout) is an
    error. No protocol-level handshake is performed for any connection type.
    """
    protocol = _PROTOCOL.get(connection_type)
    if protocol is None:
        return _failure("UNKNOWN", "Unsupported connection type")

    url = (agency.endpoint_url or "").strip()
    if not url:
        return _failure(protocol, "Endpoint URL is required")

    headers = {"User-Agent": f"{settings.USER_AGENT_PREFIX} ConnectionTest"}
    start = time.monotonic()
    response = None
    method = "HEAD"
    last_exc: Exception | None = None

    async with httpx.AsyncClient(timeout=settings.CONNECTION_TEST_TIMEOUT) as client:
        for probe_method in ("HEAD", "GET"):
            try:
                response = await getattr(client, probe_method.lower())(url, headers=headers)
                method = probe_method
                break
            except Exception as exc:
                last_exc = exc

    elapsed = int((time.monotonic() - start) * 1000)

    if response is None:
        error = (
            f"Connection timeout ({settings.CONNECTION_TEST_TIMEOUT}s)"
            if isinstance(last_exc, httpx.TimeoutException)
            else str(last_exc)
        )
        steps = [{"step": 1, "label": "TCP Connection", "status": "error", "time": elapsed}]
        return _failure(protocol, error, steps, elapsed)

    return {
        "success": True,
        "protocol": protocol,
        "version": "-",
        "steps": [
            {"step": 1, "label": "TCP Connection", "status": "done", "time": elapsed},
            {"step": 2, "label": f"{method} {response.status_code} {response.reason_phrase}", "status": "done", "time": 0},
        ],
        "latency": f"{elapsed}ms",
        "statusCode": response.status_code,
        "statusText": response.reason_phrase,
        "server": response.headers.get("server", "unknown"),
        "contentType": response.headers.get("content-type", "unknown").split(";")[0],
    }


async def run_connection_test(agency: Agency) -> dict[str, Any]:
    """Probe `agency`, persist the reset baseline, auto-recover a rule-set
    maintenance agency on success, and record a ConnectionLog row."""
    agency.stats_reset_at = now()
    raw = await test_connection(agency.connection_type, agency)

    update_fields = ["stats_reset_at", "updated_at"]
    if raw["success"] and agency.status == "maintenance" and agency.auto_maintenance:
        agency.status = "active"
        agency.auto_maintenance = False
        update_fields += ["status", "auto_maintenance"]
    await agency.save(update_fields=update_fields)

    latency_ms = int(raw["latency"].replace("ms", ""))
    status_code = raw.get("statusCode")
    detail = sanitize_body(raw.get("error") or (f"HTTP {status_code}" if status_code else raw["protocol"]))
    await ConnectionLog.create(
        agency=agency,
        action="test",
        connection_type=agency.connection_type,
        status="success" if raw["success"] else "error",
        latency_ms=latency_ms,
        detail=detail,
    )
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

    from app.services.llm import Purpose, chat
    res = await chat(purpose=Purpose.PARSE_SPEC, messages=payload["messages"],
                     tools=payload["tools"], tool_choice=payload["tool_choice"])
    tool_call = (res.tool_calls or [{}])[0]
    args_raw = tool_call.get("function", {}).get("arguments")
    if not args_raw:
        raise ValueError("Failed to parse specification")
    return _json.loads(args_raw)
