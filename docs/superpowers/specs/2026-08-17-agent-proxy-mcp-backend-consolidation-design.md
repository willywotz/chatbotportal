# Consolidate agent-proxy and mcp-server into the Python backend

Date: 2026-08-17
Status: Draft — awaiting review

## Goal

The system has two Go services next to the Python backend:

- `agent-proxy/` — a streaming reverse proxy at `/agent-proxy/{id}`.
- `mcp-server/` — an MCP server at `/mcp-v2`.

This design moves both jobs into the Python backend. After this work the
system has one backend language (Python) and one backend service. The two
Go services are removed.

## Background

Read the code first. The result is important:

- The Python backend **already has** a complete MCP server. It is in
  `app/mcp/server.py`. It uses FastMCP. It is mounted at `/mcp`. Its
  behavior is the same as the Go `mcp-server`. The Go service was a port of
  this Python code (its own comments say so). So the Go `mcp-server` is a
  duplicate. It does not need a rewrite. It needs removal.

- The Python backend does **not** have an agent-proxy. `app/mcp/server.py`
  only *builds* the callback URL `.../agent-proxy/{id}`. The proxy that
  *receives* that call — forwards the body to the agency, streams the answer
  back, writes a `connection_logs` row, and adds one to `total_calls` — is
  only in Go. This is the real new work.

So the task is:

1. Write the agent-proxy as a Python router and service (new work).
2. Remove both Go services and their Docker and nginx wiring.
3. Change the callback path to `/api/v1/agent-proxy/{id}`.

## Decisions (from review)

- Host the proxy as a router in the existing FastAPI app. One process, one
  language.
- Drop `/mcp-v2`. Clients use `/mcp` (the existing Python MCP mount).
- Serve the proxy at `/api/v1/agent-proxy/{agency_id}`. nginx already sends
  `/api/*` to the backend, so no new nginx location is needed.

## Architecture

Clean Architecture. The router is thin. The service does the work. No
database code in the router.

### New file: `app/routers/agent_proxy.py`

- One route: all HTTP methods on `/api/v1/agent-proxy/{agency_id}`.
- The route reads the request (method, headers, body), calls the service,
  and returns a `StreamingResponse` with the upstream status and headers.
- The route does not touch the database.

### New file: `app/services/agent_proxy.py`

The service holds the proxy logic. It is a port of `agent-proxy/handler.go`.

Steps:

1. Check that `agency_id` is a UUID. If not → HTTP 400.
2. Load the agency by id. If it does not exist → HTTP 404.
3. Build the upstream request:
   - Same method and body as the incoming request.
   - Clone the incoming headers.
   - Set each agency `api_header` as `name: value`.
   - Remove every header that starts with `X-Forwarded`.
   - Inject the current W3C trace context into the headers.
4. Send the request with `httpx.AsyncClient`, timeout =
   `settings.AGENCY_CHAT_TIMEOUT` (180 s). Use `client.stream(...)` (the same
   pattern as `app/services/onechat/client.py`).
5. Stream the answer back to the caller with the upstream status code and
   headers. While streaming, keep a bounded copy of the first
   `settings.CONNECTION_LOG_BODY_MAX_CHARS` characters for the log.
6. Measure the latency in milliseconds.
7. After the stream ends:
   - If the upstream status is 2xx → call `agency_service.increment_calls`.
   - Always → write one `ConnectionLog` row with:
     - `action="proxy"`
     - `connection_type="API"`
     - `status="success"` for 2xx, else `"error"`
     - `latency_ms`
     - `detail="Query: {query}\n\nAnswer: {answer}"` (from the request
       `query` field and the bounded answer)
     - `request_body` and `response_body`, each cut to
       `CONNECTION_LOG_BODY_MAX_CHARS`
8. Set the `conversation_id` span attribute. Read it from the
   `expected_payload` field that maps to `__conversation_id__`, the same as
   the Go handler.

Errors:

- Bad UUID → 400.
- Unknown agency → 404.
- Upstream connection error or timeout → 502, and write an error
  `ConnectionLog` row.
- Any other error → 500.

Trace continuation comes for free. The global `QueryTraceparentASGI` shim
already promotes `?traceparent`/`&tracestate` query params to headers before
the route runs. So the proxy does not need the query-param fallback that the
Go code has.

### Change: `app/mcp/server.py`

`_agent_proxy_endpoint` must build the new path:

```
.../api/v1/agent-proxy/{agency_id}
```

(the old path was `.../agent-proxy/{agency_id}`). Everything else in that
function stays the same (scheme resolution, `TRACE_URL_PROBE`, trace query).

### Register the router

Add `app.include_router(agent_proxy.router, prefix="/api/v1")` in
`app/main.py`, next to the other routers.

## Streaming and the log write

This is the one hard part. The client answer must stream, but the log row
must be written after the whole answer is known. Plan:

- Use `httpx` streaming and a FastAPI `StreamingResponse` whose generator
  yields each chunk to the caller and appends a bounded prefix to an
  in-memory buffer.
- When the generator ends (in its `finally`), write the `ConnectionLog` row
  and, on success, call `increment_calls`.

This mirrors the Go `limitedWriter` + `io.MultiWriter` design: stream to the
caller, keep only a bounded prefix for the log.

## Remove the Go services

- Delete the `agent-proxy/` directory.
- Delete the `mcp-server/` directory.
- `docker-compose.yaml`:
  - Remove the `agent-proxy` and `mcp-server` services.
  - Remove their named volumes (`agent-proxy-go-modules`,
    `agent-proxy-go-build-cache`, `mcp-server-go-modules`,
    `mcp-server-go-build-cache`).
  - Remove `agent-proxy` and `mcp-server` from every `depends_on`.
- `nginx/routes.conf`:
  - Remove `location /agent-proxy/`.
  - Remove `location ^~ /mcp-v2`.
  - Update the header comment block that lists the routes.
  - `/api/v1/agent-proxy` needs no location; the existing
    `^/(api|sse|messages|mcp|docs|redoc|openapi.json)` location already
    routes it to the backend.

## Event-driven architecture — open point

The connection-log write and the `total_calls` increment stay **direct
service calls**, not domain events. Reason: the three existing connection-log
writers (`scheduler.py`, `agency.test_connection`, `chat/stream.py`) all call
`ConnectionLog.create` directly. A per-request access log is telemetry, not a
domain state change. The EDA outbox stays for real domain events (like
`agency.status_changed`).

If review wants the proxy to emit a domain event (for example
`agency.call_proxied`) through the outbox, with a consumer that writes the log
and the counter, say so and this design changes to add that event and
consumer.

## Testing (TDD)

Write the tests first. Use a fake upstream through httpx transport injection,
the same pattern as `app/services/onechat/client.py` tests.

Service tests (`tests/.../test_agent_proxy_service.py`):

- Bad UUID → 400.
- Unknown agency → 404.
- `X-Forwarded*` headers are removed from the upstream request.
- Agency `api_headers` are set on the upstream request.
- 2xx upstream → `total_calls` grows by 1 and a success log row is written.
- 5xx upstream → an error log row is written and `total_calls` does not grow.
- Connection error or timeout → 502 and an error log row.
- Long request/response bodies are cut to `CONNECTION_LOG_BODY_MAX_CHARS`.
- The upstream status, headers, and body reach the caller unchanged.

Other tests:

- Update the `_agent_proxy_endpoint` test for the new `/api/v1/agent-proxy/`
  path.
- Update the route-name inventory test to include `/api/v1/agent-proxy`.

## Out of scope

- No change to the MCP tool behavior. `app/mcp/server.py` keeps its current
  logic (only the callback path string changes).
- No change to the frontend.
- No new backend language or process.

## Compliance check

- **15-Factor**: no new service, no new config type; reuses existing env
  settings (`AGENCY_CHAT_TIMEOUT`, `TRACE_URL_PROBE`,
  `CONNECTION_LOG_BODY_MAX_CHARS`). Logs go to stdout as today.
- **Clean Architecture**: thin router, logic in a service, no ORM in the
  router.
- **Event-driven**: see the open point above.
- **Full English route names**: `/api/v1/agent-proxy/{agency_id}` — full
  words, no short forms.
- **CONTEXT.md**: update and commit at each step of the plan.
