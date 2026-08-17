"""Agent-proxy: stream a OneChat callback to the agency's real endpoint,
then record one connection log and count the call.

Port of the Go agent-proxy/handler.go into the Python backend. Trace
continuation from ?traceparent query params is done globally by the
QueryTraceparentASGI shim (app/trace_util.py), so it is not repeated here.
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator, Mapping

import httpx
from fastapi import HTTPException, status
from opentelemetry import trace
from opentelemetry.propagate import inject

from app.config import settings
from app.models import Agency, ConnectionLog
from app.services import agency as agency_service

_HOP_BY_HOP = {"content-length", "content-encoding", "transfer-encoding", "connection"}


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _safe_json(body: bytes) -> dict:
    try:
        parsed = json.loads(body or b"{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _upstream_headers(incoming: Mapping[str, str], api_headers: list[dict] | None) -> dict[str, str]:
    headers = {k: v for k, v in incoming.items() if not k.lower().startswith("x-forwarded")}
    for header in api_headers or []:
        name = header.get("name")
        if name:
            headers[name] = header.get("value", "")
    inject(headers)  # W3C trace context
    return headers


def _conversation_id(expected_payload: dict | None, body_json: dict) -> str | None:
    for key, placeholder in (expected_payload or {}).items():
        if placeholder == "__conversation_id__":
            value = body_json.get(key)
            return str(value) if value not in (None, "") else None
    return None


def _truncate(text: str) -> str:
    limit = settings.CONNECTION_LOG_BODY_MAX_CHARS
    return text if len(text) <= limit else text[:limit]


async def _log(agency: Agency, log_status: str, latency_ms: int, request_body: bytes, answer: str, detail: str) -> None:
    await ConnectionLog.create(
        agency=agency,
        action="proxy",
        connection_type="API",
        status=log_status,
        latency_ms=latency_ms,
        detail=_truncate(detail),
        request_body=_truncate(request_body.decode(errors="replace")),
        response_body=_truncate(answer),
    )


async def proxy(
    *,
    agency_id: str,
    method: str,
    headers: Mapping[str, str],
    body: bytes,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[int, httpx.Headers, AsyncIterator[bytes]]:
    if not _is_uuid(agency_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid id format")
    agency = await agency_service.get_agency_or_404(uuid.UUID(agency_id))

    body_json = _safe_json(body)
    conversation_id = _conversation_id(agency.expected_payload, body_json)
    if conversation_id:
        trace.get_current_span().set_attribute("conversation_id", conversation_id)

    upstream_headers = _upstream_headers(headers, agency.api_headers)
    client = httpx.AsyncClient(timeout=settings.AGENCY_CHAT_TIMEOUT, transport=transport)
    started = time.monotonic()
    request = client.build_request(method, agency.endpoint_url or "", headers=upstream_headers, content=body)
    try:
        response = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        await client.aclose()
        await _log(agency, "error", latency_ms, body, "", f"error forwarding request: {exc}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Bad Gateway")

    async def stream() -> AsyncIterator[bytes]:
        limit = settings.CONNECTION_LOG_BODY_MAX_CHARS
        captured = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                if len(captured) < limit:
                    captured.extend(chunk[: limit - len(captured)])
                yield chunk
        finally:
            latency_ms = int((time.monotonic() - started) * 1000)
            await response.aclose()
            await client.aclose()
            answer = captured.decode(errors="replace")
            ok = 200 <= response.status_code < 300
            if ok:
                await agency_service.increment_calls(agency)
            query = body_json.get("query", "")
            await _log(
                agency, "success" if ok else "error", latency_ms, body, answer,
                f"Query: {query}\n\nAnswer: {answer}",
            )

    return response.status_code, response.headers, stream()
