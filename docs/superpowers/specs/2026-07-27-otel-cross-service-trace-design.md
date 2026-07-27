# OpenTelemetry cross-service trace propagation

**Date:** 2026-07-27
**Status:** Approved (design)
**Scope:** This project only (`backend`, `agent-proxy`). OneChat is a black box and is NOT modified.

## Goal

Make one OpenTelemetry trace ID span the full request round-trip:

```
user -> portal -> onechat -> portal(mcp) -> portal(agent-proxy) -> onechat -> portal -> user
```

Root span originates at the Portal backend (`POST /api/v1/chat/stream`). No frontend
changes.

## Constraint / the crux

The flow crosses **into OneChat twice** (Portal->OneChat, then OneChat->MCP and
OneChat->agent-proxy). A single trace ID can only survive those hops if OneChat forwards
the W3C `traceparent` header it receives. We cannot touch OneChat, so this is unknown and
uncontrollable.

Therefore the design is **robust to both outcomes**:

1. **Real W3C propagation** on every hop we own, so if OneChat forwards `traceparent`
   the whole flow shares one trace ID.
2. **Correlation fallback**: stamp `conversation_id` (already flowing through the system)
   as a span attribute on every service's spans, so the trace fragments are pivotable by
   tag in Jaeger even when the IDs differ.

> Note: true OTel *span links* need the peer `SpanContext`, which we do not have if
> `traceparent` is stripped. The realistic fallback is a shared correlation **attribute**,
> not a `Link`.

## Current state (why it's broken today)

| Hop | Owned | Today |
| --- | --- | --- |
| User -> Portal | yes | Frontend sends no `traceparent` (out of scope) |
| Portal `/api/v1/chat/stream` | yes | FastAPI auto-instrumented -> extracts incoming context (OK) |
| Portal -> OneChat | yes | `OneChatClient` sends only `Content-Type`; no `HTTPXClientInstrumentor` -> no `traceparent` injected |
| OneChat -> Portal MCP | yes | `/mcp` is a mounted Starlette sub-app (`app.mount("/mcp", mcp_app)`); FastAPIInstrumentor never covers mounts -> no server span, no extraction |
| OneChat -> agent-proxy | yes | Go `initTracer` never sets a propagator -> default no-op -> `ServeHTTP` starts a fresh trace |
| agent-proxy -> agency | yes | `r.Header.Clone()` passes an inbound `traceparent` through by luck; own span disconnected |

## Design

### Component 1 — Backend OTel bootstrap (`backend/app/main.py`)
- Add `HTTPXClientInstrumentor().instrument()` alongside the existing `TracerProvider`
  setup. Auto-injects `traceparent` on every outbound httpx call (OneChat, `dispatch_api`
  -> agent-proxy, LLM) and creates client spans.
- Rationale for auto over manual: `OneChatClient` docstring states "no tracing lives
  here"; auto-instrumentation honors that boundary (no edits to `client.py`) and covers
  all httpx callers, not just OneChat.
- Default propagator is W3C `TraceContext` (opentelemetry-python default) — confirm, do
  not override.

### Component 2 — Portal chat span (`backend/app/services/chat/stream.py`)
- Wrap the `get_client(version).events(...)` loop in `_stream_live` with an explicit span
  carrying `conversation_id` as an attribute (the correlation tag).
- `chat_stream` already tags `conversation_id` on the root span (`routers/chat.py`), so
  the root is covered.

### Component 3 — MCP inbound (`backend/app/main.py`, `backend/app/mcp/server.py`)
- Wrap the mounted sub-app with ASGI instrumentation:
  `app.mount("/mcp", OpenTelemetryMiddleware(mcp_app))` so an incoming `traceparent` on the
  OneChat->MCP callback continues the trace and produces a server span.
- Leave the main-app `excluded_urls` unchanged (avoids double-instrumenting).
- In `AuthMiddleware.on_request` / `_fetch_agencies`, stamp `conversation_id` on the
  current span.

### Component 4 — agent-proxy (Go: `agent-proxy/main.go`, `agent-proxy/handler.go`)
- `initTracer`: add
  `otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(propagation.TraceContext{}, propagation.Baggage{}))`.
  This is the single biggest break today (default is no-op).
- `ServeHTTP`: extract before starting the span —
  `ctx := otel.GetTextMapPropagator().Extract(r.Context(), propagation.HeaderCarrier(r.Header))`
  then `h.tracer.Start(ctx, ...)`.
- After building the upstream `req` (post `Header.Clone()` / X-Forwarded strip):
  `otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(req.Header))` so the
  proxy span parents the agency call.
- Parse `conversation_id` from the request body (the handler already unmarshals `query`;
  add the field) and stamp it as a span attribute.

### Component 5 — Verification
- **Backend (pytest):**
  - Capturing-transport test asserting the outbound OneChat request carries a
    `traceparent` header.
  - Test POSTing to `/mcp` with a known `traceparent`, asserting the MCP server span's
    parent trace ID matches.
- **agent-proxy (Go):** extend `TestServeHTTP_SuccessProxiesUpstream` to assert the
  upstream request's `traceparent` shares the trace ID of a supplied inbound `traceparent`.
- **Jaeger runbook (manual E2E):** inject a known `traceparent` at
  `/api/v1/chat/stream`, run the full flow, inspect whether the OneChat->MCP and
  OneChat->agent-proxy fragments share the ID (proves whether OneChat forwards). The
  `conversation_id` tag joins them either way.

## Data flow after changes

```
chat_stream (root, trace=T, tag conv=C)
  └─httpx→ OneChat   [traceparent: T injected]            (we control)
        └─ OneChat →/mcp  [T iff OneChat forwards]  → MCP span continues T (else T', both tagged conv=C)
        └─ OneChat →/agent-proxy [T iff forwarded]  → proxy extracts → agency [T injected], tagged conv=C
```

- OneChat forwards `traceparent` -> one trace ID `T` end-to-end.
- OneChat drops it -> fragments with distinct IDs, all pivotable by `conversation_id=C`.

This is the maximum achievable while touching only this project.

## Out of scope
- Frontend / browser-originated trace (user -> portal remains an untraced client hop).
- Any change to OneChat.
- Metrics/logs correlation (traces only).

## Testing / process notes
- TDD is mandatory (repo `CLAUDE.md`): failing test -> minimal code -> pass -> refactor.
- Work on branch `feat/otel-cross-service-trace`.
- Watch for existing tests that assert exact outbound httpx headers — auto-instrumentation
  adds `traceparent`; update those assertions.
