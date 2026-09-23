from typing import Any

import httpx
import time

from app.core.config import settings

_PROTOCOL = {"API": "REST API", "MCP": "MCP", "A2A": "A2A"}


def _failure(protocol: str, error: str, steps: list[dict] | None = None, latency_ms: int = 0) -> dict[str, Any]:
    return {"success": False, "protocol": protocol, "version": "-", "steps": steps or [],
            "latency": f"{latency_ms}ms", "error": error}


async def probe_reachability(connection_type: str, endpoint_url: str | None) -> dict[str, Any]:
    """Reachability probe: GET with a HEAD fallback.

    Any HTTP response — including 4xx/5xx — means the endpoint is reachable and
    counts as success. Only a transport failure (refused, DNS, timeout) is an
    error. No protocol-level handshake is performed for any connection type.

    Lives in core (primitive signature, no feature dependency) so both the
    manual test endpoint and the uptime monitor call it without either feature
    importing the other's service.
    """
    protocol = _PROTOCOL.get(connection_type)
    if protocol is None:
        return _failure("UNKNOWN", "Unsupported connection type")

    url = (endpoint_url or "").strip()
    if not url:
        return _failure(protocol, "Endpoint URL is required")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"}
    start = time.monotonic()
    response = None
    method = "GET"
    last_exc: Exception | None = None

    async with httpx.AsyncClient(timeout=settings.CONNECTION_TEST_TIMEOUT) as client:
        for probe_method in ("GET", "HEAD"):
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
        steps = [{"step": 1, "label": "TCP Connection", "status": "error", "time_ms": elapsed}]
        return _failure(protocol, error, steps, elapsed)

    return {
        "success": True,
        "protocol": protocol,
        "version": "-",
        "steps": [
            {"step": 1, "label": "TCP Connection", "status": "done", "time_ms": elapsed},
            {"step": 2, "label": f"{method} {response.status_code} {response.reason_phrase}", "status": "done", "time_ms": 0},
        ],
        "latency": f"{elapsed}ms",
        "statusCode": response.status_code,
        "statusText": response.reason_phrase,
        "server": response.headers.get("server", "unknown"),
        "contentType": response.headers.get("content-type", "unknown").split(";")[0],
    }
