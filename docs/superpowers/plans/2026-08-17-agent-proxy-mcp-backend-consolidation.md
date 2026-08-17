# Agent-Proxy + MCP Backend Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Go `agent-proxy` and `mcp-server` jobs into the Python backend so the system has one backend language (Python) and one backend service.

**Architecture:** The Python backend already has a behavior-equivalent MCP server (`app/mcp/server.py`, mounted at `/mcp`), so the Go `mcp-server` is only removed, not rewritten. The Go `agent-proxy` has no Python twin, so it is rewritten as a thin FastAPI router that delegates to a new service (`app/services/agent_proxy.py`). The proxy is an external OneChat callback with no portal-role auth, so it bypasses the role chokepoint.

**Tech Stack:** Python 3, FastAPI, Tortoise ORM, httpx (streaming, transport injection for tests), OpenTelemetry, pytest.

**Spec:** `docs/superpowers/specs/2026-08-17-agent-proxy-mcp-backend-consolidation-design.md`

## Global Constraints

- ASD-STE100 Simplified Technical English in all prose (comments, docs, `CONTEXT.md`).
- Clean Architecture: routers stay thin; no ORM/query code in routers. Logic lives in services.
- Full English route names, no short forms: the route is `/api/v1/agent-proxy/{agency_id}`.
- TDD is mandatory: write the failing test, confirm it fails, write minimal code, confirm it passes.
- Reuse existing helpers: `agency_service.get_agency_or_404`, `agency_service.increment_calls`, `ConnectionLog.create`, `settings.AGENCY_CHAT_TIMEOUT` (180), `settings.CONNECTION_LOG_BODY_MAX_CHARS` (4096), `settings.TRACE_URL_PROBE`.
- EDA scope: the connection-log write and `total_calls` increment are **direct service calls**, not domain events (matches the three existing `ConnectionLog.create` writers). Do not add an outbox event for the proxy.
- **Orchestrator owns `CONTEXT.md` + git.** After each task passes its tests and review, the orchestrator updates `CONTEXT.md` (ASD-STE100) and commits. Builders produce code + tests only. The "Commit" step in each task is performed by the orchestrator.
- Run the whole backend suite from `backend/` with `.venv` active: `cd backend && python -m pytest`.

---

### Task 1: Agent-proxy service

The core port of `agent-proxy/handler.go`. Validates the id, loads the agency, forwards the request to the agency's real `endpoint_url`, streams the answer back, then writes one `ConnectionLog` row and counts the call.

**Files:**
- Create: `backend/app/services/agent_proxy.py`
- Test: `backend/tests/services/test_agent_proxy.py`

**Interfaces:**
- Consumes: `agency_service.get_agency_or_404(agency_id: UUID) -> Agency`, `agency_service.increment_calls(agency: Agency) -> Agency`, `ConnectionLog.create(...)`, `settings.AGENCY_CHAT_TIMEOUT`, `settings.CONNECTION_LOG_BODY_MAX_CHARS`.
- Produces:
  ```python
  async def proxy(
      *,
      agency_id: str,
      method: str,
      headers: Mapping[str, str],
      body: bytes,
      transport: httpx.AsyncBaseTransport | None = None,
  ) -> tuple[int, httpx.Headers, AsyncIterator[bytes]]
  ```
  Raises `HTTPException` 400 (bad id), 404 (unknown agency), 502 (upstream error). `transport` is a test seam (inject `httpx.MockTransport`); production passes `None`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/test_agent_proxy.py`. Use `httpx.MockTransport` as the fake upstream. `db` fixture (see `tests/conftest.py`) gives an in-memory DB; create an `Agency` per test.

```python
import json
import uuid

import httpx
import pytest
from fastapi import HTTPException

from app.models import Agency, ConnectionLog
from app.services import agent_proxy


async def _agency(**over):
    data = dict(
        name="Dept", connection_type="API", status="active",
        endpoint_url="http://upstream.test/chat",
        expected_payload={"query": "{q}", "session_id": "__conversation_id__"},
        api_headers=[{"name": "Authorization", "value": "Bearer up-secret"}],
    )
    data.update(over)
    return await Agency.create(**data)


def _upstream(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def _drain(stream) -> bytes:
    out = bytearray()
    async for chunk in stream:
        out.extend(chunk)
    return bytes(out)


async def test_bad_uuid_raises_400(db):
    with pytest.raises(HTTPException) as e:
        await agent_proxy.proxy(agency_id="not-a-uuid", method="POST", headers={}, body=b"{}")
    assert e.value.status_code == 400


async def test_unknown_agency_raises_404(db):
    with pytest.raises(HTTPException) as e:
        await agent_proxy.proxy(
            agency_id=str(uuid.uuid4()), method="POST", headers={}, body=b"{}",
        )
    assert e.value.status_code == 404


async def test_success_streams_body_and_status(db):
    agency = await _agency()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hello-answer")

    status_code, _headers, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    body = await _drain(stream)
    assert status_code == 200
    assert body == b"hello-answer"


async def test_success_increments_calls_and_logs(db):
    agency = await _agency(total_calls=0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    _sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    await _drain(stream)
    await agency.refresh_from_db()
    assert agency.total_calls == 1
    log = await ConnectionLog.filter(agency_id=agency.id).first()
    assert log.action == "proxy"
    assert log.connection_type == "API"
    assert log.status == "success"
    assert "Query: hi" in log.detail


async def test_strips_x_forwarded_and_sets_api_headers(db):
    agency = await _agency()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, content=b"ok")

    _sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST",
        headers={"X-Forwarded-For": "1.2.3.4", "X-Forwarded-Host": "x", "Accept": "*/*"},
        body=b"{}", transport=_upstream(handler),
    )
    await _drain(stream)
    assert not any(k.lower().startswith("x-forwarded") for k in seen)
    assert seen.get("authorization") == "Bearer up-secret"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_agent_proxy.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.agent_proxy` (or `AttributeError: proxy`).

- [ ] **Step 3: Write the service**

Create `backend/app/services/agent_proxy.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_agent_proxy.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Add the error-path tests**

Append to `backend/tests/services/test_agent_proxy.py`:

```python
async def test_upstream_5xx_logs_error_and_no_increment(db):
    agency = await _agency(total_calls=0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"down")

    sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    await _drain(stream)
    await agency.refresh_from_db()
    assert sc == 503
    assert agency.total_calls == 0
    log = await ConnectionLog.filter(agency_id=agency.id).first()
    assert log.status == "error"


async def test_connection_error_raises_502_and_logs(db):
    agency = await _agency()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(HTTPException) as e:
        await agent_proxy.proxy(
            agency_id=str(agency.id), method="POST", headers={},
            body=b"{}", transport=_upstream(handler),
        )
    assert e.value.status_code == 502
    log = await ConnectionLog.filter(agency_id=agency.id).first()
    assert log.status == "error"


async def test_response_body_truncated_in_log(db, monkeypatch):
    monkeypatch.setattr(agent_proxy.settings, "CONNECTION_LOG_BODY_MAX_CHARS", 10)
    agency = await _agency()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 100)

    _sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    assert await _drain(stream) == b"x" * 100  # caller still gets the full body
    log = await ConnectionLog.filter(agency_id=agency.id).first()
    assert len(log.response_body) == 10
```

- [ ] **Step 6: Run the full service test file**

Run: `cd backend && python -m pytest tests/services/test_agent_proxy.py -v`
Expected: PASS (8 tests). If `test_connection_error_raises_502_and_logs` fails because `MockTransport` wraps the raise, confirm the service catches `httpx.HTTPError` (‎`ConnectError` is a subclass).

- [ ] **Step 7: Commit** (orchestrator: update `CONTEXT.md` first)

```bash
git add backend/app/services/agent_proxy.py backend/tests/services/test_agent_proxy.py CONTEXT.md
git commit -m "feat(agent-proxy): port streaming reverse proxy to a Python service"
```

---

### Task 2: Router, registration, and auth bypass

Expose the service at `/api/v1/agent-proxy/{agency_id}` for all methods, register it, and let the external OneChat callback pass the role chokepoint. Update the parity tests that pin the auth surface.

**Files:**
- Create: `backend/app/routers/agent_proxy.py`
- Modify: `backend/app/main.py` (add `include_router`)
- Modify: `backend/app/auth/dependencies.py` (bypass the proxy path)
- Test: `backend/tests/routers/test_agent_proxy_router.py`
- Modify (as tests demand): `backend/tests/test_surface_parity.py`, `backend/tests/test_staff_allowlist.py`, `backend/tests/test_basic_user_allowlist.py`

**Interfaces:**
- Consumes: `agent_proxy.proxy(...)` from Task 1.
- Produces: `router` (APIRouter, prefix `/agent-proxy`, registered under `/api/v1`); a module-level regex `_AGENT_PROXY_PATTERN` in `dependencies.py`.

- [ ] **Step 1: Write the failing router test**

Create `backend/tests/routers/test_agent_proxy_router.py`. Drive the real ASGI app with `httpx.ASGITransport`, and inject the fake upstream by monkeypatching the service's transport-less `proxy` to force a `MockTransport`.

```python
import json
import uuid

import httpx
import pytest

from app.main import app
from app.models import Agency
from app.services import agent_proxy


@pytest.fixture
def fake_upstream(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"agency-answer")

    real = agent_proxy.proxy

    async def patched(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return await real(**kwargs)

    monkeypatch.setattr(agent_proxy, "proxy", patched)


async def _agency() -> Agency:
    return await Agency.create(
        name="Dept", connection_type="API", status="active",
        endpoint_url="http://upstream.test/chat",
        expected_payload={"query": "{q}"}, api_headers=[],
    )


async def test_proxy_route_streams_without_portal_auth(db, fake_upstream):
    agency = await _agency()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/agent-proxy/{agency.id}",
            content=json.dumps({"query": "hi"}),
        )
    assert resp.status_code == 200
    assert resp.content == b"agency-answer"


async def test_proxy_route_bad_uuid_returns_400(db, fake_upstream):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agent-proxy/not-a-uuid", content=b"{}")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/routers/test_agent_proxy_router.py -v`
Expected: FAIL — 404 (route not registered) instead of 200/400.

- [ ] **Step 3: Write the router**

Create `backend/app/routers/agent_proxy.py`:

```python
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
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, add the import next to the other router imports and register it with the other `include_router` calls (near line 141–159):

```python
from app.routers import agent_proxy
...
app.include_router(agent_proxy.router, prefix="/api/v1")
```

- [ ] **Step 5: Add the chokepoint bypass**

In `backend/app/auth/dependencies.py`, near the other path patterns (after `_AGENCY_LOGO_GET_PATTERN`, ~line 57):

```python
# Agent-proxy is an external OneChat callback, not a portal-user request. It
# carries no portal API key, so it must bypass the role allowlist for every
# method — the same "no portal-role auth" contract the Go agent-proxy had.
_AGENT_PROXY_PATTERN = re.compile(r"^/api/v1/agent-proxy/[^/]+$")
```

In `enforce_role_allowlist`, right after the `if _is_public_get(method, path): return` line (~line 253):

```python
    if _AGENT_PROXY_PATTERN.match(path):
        return
```

- [ ] **Step 6: Run the router test to verify it passes**

Run: `cd backend && python -m pytest tests/routers/test_agent_proxy_router.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Update the surface-parity tests for the new public route**

The new route is now reachable by every role, so the pinned per-role surfaces must include it. Run the three parity tests:

Run: `cd backend && python -m pytest tests/test_surface_parity.py tests/test_staff_allowlist.py tests/test_basic_user_allowlist.py -v`

For each test that fails because `/api/v1/agent-proxy/{id}` appears in `reachable` but not in the expected set, add the proxy routes to the expected set the same way the file already enumerates `auth_routes`/`public_gets` from the route table. In `tests/test_surface_parity.py::test_user_surface_is_exactly_this`, add:

```python
    agent_proxy_routes = {
        (m, p) for m, p in _concrete_paths() if p.startswith("/api/v1/agent-proxy/")
    }
```

and union it into the final expected set alongside `auth_routes`, `public_gets`, `logo_gets` (find the line that unions those and add `| agent_proxy_routes`). Apply the same enumerate-and-union fix to `test_staff_allowlist.py` and `test_basic_user_allowlist.py` only where a run fails.

- [ ] **Step 8: Run the parity tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_surface_parity.py tests/test_staff_allowlist.py tests/test_basic_user_allowlist.py -v`
Expected: PASS.

- [ ] **Step 9: Commit** (orchestrator: update `CONTEXT.md` first)

```bash
git add backend/app/routers/agent_proxy.py backend/app/main.py backend/app/auth/dependencies.py backend/tests/routers/test_agent_proxy_router.py backend/tests/test_surface_parity.py backend/tests/test_staff_allowlist.py backend/tests/test_basic_user_allowlist.py CONTEXT.md
git commit -m "feat(agent-proxy): expose /api/v1/agent-proxy route with public-callback bypass"
```

---

### Task 3: Point the MCP callback at the new path

`app/mcp/server.py` builds the callback URL OneChat calls back. It must now build `/api/v1/agent-proxy/{id}`.

**Files:**
- Modify: `backend/app/mcp/server.py` (`_agent_proxy_endpoint`, ~line 102)
- Test: `backend/tests/test_trace_url_probe.py` (add a path assertion)

**Interfaces:**
- Consumes: nothing new.
- Produces: `_agent_proxy_endpoint` now returns a URL whose path is `/api/v1/agent-proxy/{agency_id}`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_trace_url_probe.py`:

```python
def test_endpoint_uses_api_v1_agent_proxy_path():
    request = _request({"x-forwarded-host": "example.com", "x-forwarded-proto": "https"})
    url = _agent_proxy_endpoint(request, "11111111-1111-4111-8111-111111111111")
    assert "/api/v1/agent-proxy/11111111-1111-4111-8111-111111111111" in url
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_trace_url_probe.py::test_endpoint_uses_api_v1_agent_proxy_path -v`
Expected: FAIL — URL still contains `/agent-proxy/...` without the `/api/v1` prefix.

- [ ] **Step 3: Change the path**

In `backend/app/mcp/server.py`, in `_agent_proxy_endpoint`, change the URL line:

```python
    url = f"{_external_scheme(request)}://{request.headers.get('X-Forwarded-Host')}/api/v1/agent-proxy/{agency_id}"
```

(only `/agent-proxy/` → `/api/v1/agent-proxy/`; leave the `TRACE_URL_PROBE` and `with_trace_query` lines unchanged).

- [ ] **Step 4: Run the whole file to verify it passes**

Run: `cd backend && python -m pytest tests/test_trace_url_probe.py -v`
Expected: PASS (all existing tests + the new one; the existing tests only assert query behavior, so they stay green).

- [ ] **Step 5: Commit** (orchestrator: update `CONTEXT.md` first)

```bash
git add backend/app/mcp/server.py backend/tests/test_trace_url_probe.py CONTEXT.md
git commit -m "refactor(mcp): build the agent-proxy callback at /api/v1/agent-proxy"
```

---

### Task 4: Remove the Go services and their wiring

Delete both Go services and every Docker and nginx reference. `/api/v1/agent-proxy` needs no nginx location (nginx already routes `/api/*` to the backend). `/mcp-v2` is dropped; `/mcp` stays.

**Files:**
- Delete: `agent-proxy/` (whole directory), `mcp-server/` (whole directory)
- Modify: `docker-compose.yaml`
- Modify: `nginx/routes.conf`

**Interfaces:** none (infrastructure only).

- [ ] **Step 1: Delete the Go service directories**

```bash
git rm -r agent-proxy mcp-server
```

- [ ] **Step 2: Edit `docker-compose.yaml`**

- Remove the whole `agent-proxy:` service block (~lines 86–109) and the whole `mcp-server:` service block (~lines 111–138).
- Remove the four named volumes at the bottom: `agent-proxy-go-modules`, `agent-proxy-go-build-cache`, `mcp-server-go-modules`, `mcp-server-go-build-cache`.
- Remove `agent-proxy` and `mcp-server` from every `depends_on` (the `backend` service and the `nginx` service reference them).

- [ ] **Step 3: Edit `nginx/routes.conf`**

- Delete the `location /agent-proxy/ { ... }` block (~lines 62–69).
- Delete the `location ^~ /mcp-v2 { ... }` block (~lines 32–44).
- Update the header comment (lines 3–6) to drop the `/mcp-v2` and `/agent-proxy/` lines; the backend line already covers `/api`, which now serves the proxy.

- [ ] **Step 4: Verify the compose file still parses and no stale references remain**

Run:
```bash
docker compose -f docker-compose.yaml config >/dev/null && echo COMPOSE_OK
grep -rnE 'agent-proxy|mcp-server|mcp-v2' docker-compose.yaml nginx/ ; echo "grep-done (want: only comments, if any)"
```
Expected: `COMPOSE_OK`; the grep shows no active service/route references (comments that describe history are acceptable, but prefer none).

- [ ] **Step 5: Commit** (orchestrator: update `CONTEXT.md` first)

```bash
git add -A
git commit -m "chore: remove Go agent-proxy and mcp-server; drop /mcp-v2 and /agent-proxy nginx routes"
```

---

### Task 5: Full verification and final `CONTEXT.md`

**Files:**
- Modify: `CONTEXT.md`

- [ ] **Step 1: Run the whole backend suite**

Run: `cd backend && python -m pytest`
Expected: all pass (the pre-change baseline on `main` was 839 passed / 6 skipped; this adds the new agent-proxy tests). If any pre-existing test asserts the old `/agent-proxy/` root path or `/mcp-v2`, fix it to the new contract.

- [ ] **Step 2: Confirm no source references the removed services**

Run: `grep -rnE 'mcp-v2|/agent-proxy/' backend/app nginx docker-compose.yaml | grep -v '/api/v1/agent-proxy'`
Expected: no hits (every proxy path is now `/api/v1/agent-proxy/...`).

- [ ] **Step 3: Final `CONTEXT.md` update and commit**

Record the consolidation in ASD-STE100: one backend language (Python); the Go `agent-proxy` is now `app/services/agent_proxy.py` + `app/routers/agent_proxy.py` at `/api/v1/agent-proxy/{agency_id}`; the Go `mcp-server` is removed because `app/mcp/server.py` already serves `/mcp`; `/mcp-v2` is dropped.

```bash
git add CONTEXT.md
git commit -m "docs: record agent-proxy + mcp-server backend consolidation"
```

---

## Self-Review

**Spec coverage:**
- New `app/routers/agent_proxy.py` + `app/services/agent_proxy.py` → Tasks 1–2. ✓
- Proxy behavior (UUID→400, 404, header clone, `X-Forwarded` strip, `api_headers`, trace inject, 180s stream, status/header passthrough, `increment_calls`, `ConnectionLog` write, `conversation_id` span, 502) → Task 1. ✓
- Register router → Task 2. ✓
- Callback path change in `server.py` → Task 3. ✓
- Remove Go services + docker-compose + nginx → Task 4. ✓
- Drop `/mcp-v2`, keep `/mcp` → Task 4. ✓
- EDA decision (direct service calls) → Global Constraints + Task 1. ✓
- Tests (fake upstream, all listed cases; `_agent_proxy_endpoint` test; route-name/parity) → Tasks 1–3, plus the surface-parity update in Task 2 (found during planning — the proxy is a public callback that changes the pinned auth surface). ✓

**Extra items found during planning (not in the spec, but required):**
- Chokepoint bypass for the public callback (Task 2, Steps 5) — the Go proxy had no caller auth; without this a non-anonymous caller would 403.
- Hop-by-hop header stripping on the `StreamingResponse` (Task 2 router + service `_HOP_BY_HOP`) — avoids Content-Length/Content-Encoding mismatch when re-streaming.

**Placeholder scan:** none — every code step has concrete code.

**Type consistency:** `proxy(...) -> tuple[int, httpx.Headers, AsyncIterator[bytes]]` is produced in Task 1 and consumed unchanged by the Task 2 router and the Task 2 test. `_AGENT_PROXY_PATTERN` is defined and used within Task 2. `action="proxy"`, `connection_type="API"` match across service and tests.
