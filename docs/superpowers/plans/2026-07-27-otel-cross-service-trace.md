# OTel Cross-Service Trace Propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate a single W3C trace context across Portal backend and agent-proxy for the OneChat chat flow, with a `conversation_id` correlation-tag fallback for the OneChat black-box hops.

**Architecture:** Auto-inject `traceparent` on all backend outbound httpx; instrument the mounted `/mcp` Starlette sub-app for inbound extraction; set a propagator + extract/inject in the Go agent-proxy. Stamp `conversation_id` as a span attribute on every service so fragments join in Jaeger even if OneChat strips the header.

**Tech Stack:** Python 3, FastAPI, opentelemetry-python (fastapi + httpx + asgi instrumentation), httpx; Go, go.opentelemetry.io/otel v1.43.0.

## Global Constraints

- TDD mandatory: failing test → confirm fail → minimal code → confirm pass → refactor.
- Branch: `feat/otel-cross-service-trace` (already created).
- Use `rtk` prefix for shell/git commands.
- Do NOT modify OneChat. Only `backend/` and `agent-proxy/`.
- Do NOT override the default W3C `TraceContext` propagator in Python (it is the default).
- Google style guides; American English; organized imports.

---

## Amendments (applied during execution)

Two of the test snippets below could not produce a genuine TDD red state as
originally written; both were corrected during implementation, and a new
decision was added for the agent-proxy correlation tag. The committed code
reflects these amendments (not the original snippets in Tasks 1 and 4).

1. **Task 1 test** — `httpx.MockTransport` is a *sibling* of `AsyncHTTPTransport`,
   which is the only class `HTTPXClientInstrumentor().instrument()` patches, so a
   MockTransport-based test never observes injection. The test was rewritten to
   run against a real loopback `http.server` (default `AsyncHTTPTransport`) and to
   import `app.main` so it exercises the production wiring. Red proof: commenting
   out the `instrument()` line flips it to fail.
2. **Task 4 test** — the existing `req.Header = r.Header.Clone()` already forwards
   an inbound `traceparent` byte-for-byte, so a trace-id-only assertion passes
   before any change. The test now also asserts the upstream **span-id differs**
   from the inbound span-id, proving a real child span was created (extract →
   Start → inject) rather than raw pass-through.
3. **Task 4b (new) — agent-proxy conversation_id source.** The body field carrying
   the id varies per agency (`session_id` / `conv_id` / `conversation_id`) because
   it follows each agency's `expected_payload` template (which maps the
   `__conversation_id__` placeholder; the MCP server substitutes only a returned
   copy, so the DB template retains the placeholder). agent-proxy now loads
   `expected_payload` from the DB, finds the key mapped to `__conversation_id__`,
   and reads that field from the request body — replacing the hardcoded
   `conversation_id` field. Behavioral test via a Go `tracetest.SpanRecorder`.
   Known minor: the mapped value is stringified with `fmt.Sprint`; a JSON-null or
   huge-number field would render oddly (unreachable for string-UUID ids) — a
   future type-assert hardening, not blocking.

---

### Task 1: Backend outbound httpx propagation

**Files:**
- Modify: `backend/pyproject.toml` (add dependency)
- Modify: `backend/app/main.py:44-61` (OTel bootstrap block)
- Test: `backend/tests/services/onechat/test_client_traceparent.py` (create)

**Interfaces:**
- Consumes: existing `OneChatClient(base_url, transport=...)` from `app.services.onechat`.
- Produces: after this task, any outbound `httpx` request made inside an active span carries a `traceparent` header. No new public symbols.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/onechat/test_client_traceparent.py
import httpx
import pytest
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from app.services.onechat import OneChatClient


@pytest.fixture
def _instrument_httpx():
    HTTPXClientInstrumentor().instrument()
    yield
    HTTPXClientInstrumentor().uninstrument()


async def test_onechat_request_carries_traceparent(_instrument_httpx):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["traceparent"] = request.headers.get("traceparent")
        return httpx.Response(200, json={"data": {"answer": "x"}})

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler), version="v3")
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("root") as span:
        expected = format(span.get_span_context().trace_id, "032x")
        _ = [ev async for ev in client.events("q", "http://mcp", "c")]

    assert captured["traceparent"] is not None, "no traceparent injected on OneChat call"
    assert expected in captured["traceparent"], "traceparent trace id does not match active span"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && rtk pytest tests/services/onechat/test_client_traceparent.py -v`
Expected: FAIL — `ModuleNotFoundError: opentelemetry.instrumentation.httpx` (dependency not yet installed).

- [ ] **Step 3: Add the dependency**

In `backend/pyproject.toml`, add to the dependencies list (keep it sorted near the other `opentelemetry-instrumentation-*` entries):

```toml
"opentelemetry-instrumentation-httpx>=0.62b1",
```

Then install into the environment: `cd backend && rtk uv sync` (or the project's usual install command, e.g. rebuild the backend image).

- [ ] **Step 4: Wire the instrumentor in the OTel bootstrap**

In `backend/app/main.py`, in the OTel block (around lines 44-61), after `trace.set_tracer_provider(tracerProvider)` add:

```python
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
HTTPXClientInstrumentor().instrument()
```

(Do NOT edit `app/services/onechat/client.py` — it intentionally holds no tracing.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && rtk pytest tests/services/onechat/test_client_traceparent.py -v`
Expected: PASS.

- [ ] **Step 6: Run the OneChat client suite to catch header-assert regressions**

Run: `cd backend && rtk pytest tests/services/onechat -v`
Expected: PASS. If any test asserts exact outbound headers, relax it to ignore the added `traceparent`/`tracestate`.

- [ ] **Step 7: Commit**

```bash
rtk git add backend/pyproject.toml backend/app/main.py backend/tests/services/onechat/test_client_traceparent.py
rtk git commit -m "feat(trace): inject W3C traceparent on backend outbound httpx"
```

---

### Task 2: Correlation tag on the OneChat call span

**Files:**
- Modify: `backend/app/services/chat/stream.py:137-192` (`_stream_live`)
- Test: `backend/tests/services/test_chat_turn_stream.py` (add a test) — or create `backend/tests/services/test_stream_trace_tag.py`

**Interfaces:**
- Consumes: `TurnPlan` with `.conversation_id`, `.query`, `.stream_version`; `get_client(version).events(...)` from `app.services.onechat`.
- Produces: a span named `onechat_call` with attribute `conversation_id` wrapping the OneChat event loop.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_stream_trace_tag.py
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.main as main  # ensures tracer provider is configured
from app.services.chat.stream import _stream_live
from app.services.onechat import OneChatClient
import app.services.chat.stream as stream_mod


async def test_onechat_span_tags_conversation_id(monkeypatch):
    exporter = InMemorySpanExporter()
    main.tracerProvider.add_span_processor(SimpleSpanProcessor(exporter))

    async def fake_events(query, mcp_url, session_id):
        yield ("answer", {"answer": "hi"})
        yield ("done", {"session_id": session_id, "total_ms": 1})

    class _Stub:
        def events(self, *a, **k):
            return fake_events(*a, **k)

    monkeypatch.setattr(stream_mod, "get_client", lambda v: _Stub())
    monkeypatch.setattr(stream_mod, "_persist", _noop_persist := _make_noop())

    plan = _make_plan(conversation_id="conv-xyz")  # helper mirroring existing stream tests
    _ = [ev async for ev in _stream_live(plan, background_tasks=None)]

    spans = exporter.get_finished_spans()
    tagged = [s for s in spans if s.attributes.get("conversation_id") == "conv-xyz"]
    assert any(s.name == "onechat_call" for s in tagged), "onechat_call span missing conversation_id tag"
```

> Note: reuse the `TurnPlan` construction and `_persist` monkeypatch style already used in
> `backend/tests/services/test_chat_turn_stream.py`; copy its `_make_plan`/stub helpers into
> this file rather than inventing new ones.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && rtk pytest tests/services/test_stream_trace_tag.py -v`
Expected: FAIL — no span named `onechat_call`.

- [ ] **Step 3: Wrap the event loop in a tagged span**

In `backend/app/services/chat/stream.py` `_stream_live`, wrap the `async for ... in get_client(version).events(...)` loop in a span. Using the module's existing `tracer`:

```python
with tracer.start_as_current_span("onechat_call") as call_span:
    call_span.set_attribute("conversation_id", plan.conversation_id)
    call_span.set_attribute("chat_stream_version", version)
    async for event_name, event_data in get_client(version).events(
        plan.query, settings.MCP_ENDPOINT_URL, plan.conversation_id
    ):
        ...  # existing loop body unchanged
```

Keep the existing `except OneChatError` / `except Exception` handling around it (the `with` sits inside the current `try`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && rtk pytest tests/services/test_stream_trace_tag.py -v`
Expected: PASS.

- [ ] **Step 5: Run the stream suite**

Run: `cd backend && rtk pytest tests/services/test_chat_turn_stream.py tests/routers/test_chat_stream_message_id.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/services/chat/stream.py backend/tests/services/test_stream_trace_tag.py
rtk git commit -m "feat(trace): tag OneChat call span with conversation_id"
```

---

### Task 3: MCP inbound instrumentation + correlation tag

**Files:**
- Modify: `backend/app/main.py:156-157` (the `/mcp` mount)
- Modify: `backend/app/mcp/server.py` (`AuthMiddleware.on_request`)
- Test: `backend/tests/test_mcp_trace_inbound.py` (create)

**Interfaces:**
- Consumes: `main.app` (FastAPI), `main.mcp_app` (Starlette sub-app), `OpenTelemetryMiddleware`.
- Produces: the object mounted at `/mcp` is an `OpenTelemetryMiddleware` instance; MCP request spans carry `conversation_id`.

- [ ] **Step 1: Write the failing test (wiring guard)**

```python
# backend/tests/test_mcp_trace_inbound.py
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

import app.main as main


def _mcp_mount(fastapi_app):
    for route in fastapi_app.routes:
        if getattr(route, "path", None) == "/mcp":
            return route
    raise AssertionError("/mcp mount not found")


def test_mcp_mount_is_otel_wrapped():
    mount = _mcp_mount(main.app)
    assert isinstance(mount.app, OpenTelemetryMiddleware), (
        "/mcp sub-app must be wrapped in OpenTelemetryMiddleware so an incoming "
        "traceparent on the OneChat->MCP callback continues the trace. Mounted "
        "sub-apps are never covered by FastAPIInstrumentor.instrument_app."
    )
```

> Rationale: `OpenTelemetryMiddleware`'s extract-and-continue behavior is guaranteed by the
> library; the real risk we guard is "did we actually wrap the mount." End-to-end trace-id
> continuation is validated by the Jaeger runbook in Task 5.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && rtk pytest tests/test_mcp_trace_inbound.py -v`
Expected: FAIL — `mount.app` is the raw `mcp_app`, not `OpenTelemetryMiddleware`.

- [ ] **Step 3: Wrap the mount**

In `backend/app/main.py`, change the mount and add the import near the other OTel imports:

```python
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
# ...
app.mount("/mcp", OpenTelemetryMiddleware(mcp_app))
```

Leave `excluded_urls="/health,^/health$,/mcp,^/mcp$"` unchanged (prevents the main-app instrumentor from double-spanning).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && rtk pytest tests/test_mcp_trace_inbound.py -v`
Expected: PASS.

- [ ] **Step 5: Add the conversation_id correlation tag on the MCP span**

In `backend/app/mcp/server.py`, in `AuthMiddleware.on_request`, after `conversation_id` is resolved, tag the current span:

```python
from opentelemetry import trace
# ... after conversation_id is set:
trace.get_current_span().set_attribute("conversation_id", conversation_id)
```

- [ ] **Step 6: Run MCP suites to confirm no regression**

Run: `cd backend && rtk pytest tests/test_mcp_stateless_http.py tests/test_mcp_streamable_calls.py tests/test_mcp_role_access.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
rtk git add backend/app/main.py backend/app/mcp/server.py backend/tests/test_mcp_trace_inbound.py
rtk git commit -m "feat(trace): instrument /mcp mount and tag MCP span with conversation_id"
```

---

### Task 4: agent-proxy propagator, extract, inject, correlation tag

**Files:**
- Modify: `agent-proxy/main.go:70-95` (`initTracer`)
- Modify: `agent-proxy/handler.go:59-192` (`ServeHTTP`)
- Test: `agent-proxy/handler_test.go` (add a test)

**Interfaces:**
- Consumes: `go.opentelemetry.io/otel`, `go.opentelemetry.io/otel/propagation`, `go.opentelemetry.io/otel/sdk/trace` (all already in `go.mod`).
- Produces: global propagator set to `TraceContext`+`Baggage`; `ServeHTTP` continues an inbound `traceparent` and injects it into the upstream request; span attribute `conversation_id`.

- [ ] **Step 1: Write the failing test**

```go
// add to agent-proxy/handler_test.go
func TestServeHTTP_PropagatesTraceContext(t *testing.T) {
	otel.SetTextMapPropagator(propagation.TraceContext{})
	tp := sdktrace.NewTracerProvider()
	defer func() { _ = tp.Shutdown(context.Background()) }()

	const id = "11111111-1111-4111-8111-111111111111"
	const traceID = "0af7651916cd43dd8448eb211c80319c"

	var gotTP string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotTP = r.Header.Get("traceparent")
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	h := &handler{
		tracer: tp.Tracer("test"),
		load: func(_ context.Context, _ string) (agency, error) {
			return agency{endpointURL: upstream.URL}, nil
		},
	}

	req := httptest.NewRequest(http.MethodPost, "/agent-proxy/"+id, strings.NewReader(`{"query":"q"}`))
	req.Header.Set("traceparent", "00-"+traceID+"-b7ad6b7169203331-01")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)

	if gotTP == "" {
		t.Fatalf("no traceparent injected into upstream request")
	}
	if !strings.Contains(gotTP, traceID) {
		t.Errorf("upstream traceparent should share inbound trace id %s, got %q", traceID, gotTP)
	}
}
```

Add imports to the test file: `"go.opentelemetry.io/otel"`, `"go.opentelemetry.io/otel/propagation"`, `sdktrace "go.opentelemetry.io/otel/sdk/trace"`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent-proxy && rtk go test ./... -run TestServeHTTP_PropagatesTraceContext -v`
Expected: FAIL — `gotTP == ""` (no propagator set / no extraction / no injection).

- [ ] **Step 3: Set the global propagator**

In `agent-proxy/main.go` `initTracer`, before `return tp, nil`, add:

```go
otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
	propagation.TraceContext{},
	propagation.Baggage{},
))
```

Add `"go.opentelemetry.io/otel/propagation"` to imports.

- [ ] **Step 4: Extract inbound + inject upstream in `ServeHTTP`**

In `agent-proxy/handler.go` `ServeHTTP`:

Replace the span start so it continues the extracted context:

```go
ctx := otel.GetTextMapPropagator().Extract(r.Context(), propagation.HeaderCarrier(r.Header))
ctx, span := h.tracer.Start(ctx, "Handle HTTP Request")
defer span.End()
```

After the upstream `req` is built and its headers cloned/stripped (just before `httpClient.Do(req)`), inject:

```go
otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(req.Header))
```

Add `"go.opentelemetry.io/otel"` and `"go.opentelemetry.io/otel/propagation"` to `handler.go` imports.

- [ ] **Step 5: Add the conversation_id correlation tag**

The handler already unmarshals the body into `var raw struct{ Query string ... }`. Extend it and tag the span:

```go
var raw struct {
	Query          string `json:"query"`
	ConversationID string `json:"conversation_id"`
}
_ = json.Unmarshal(body.Bytes(), &raw)
if raw.ConversationID != "" {
	span.SetAttributes(attribute.String("conversation_id", raw.ConversationID))
}
```

(`attribute` is already imported in `handler.go`.)

- [ ] **Step 6: Run test to verify it passes**

Run: `cd agent-proxy && rtk go test ./... -run TestServeHTTP_PropagatesTraceContext -v`
Expected: PASS.

- [ ] **Step 7: Run the full agent-proxy suite**

Run: `cd agent-proxy && rtk go test ./...`
Expected: PASS (existing `TestServeHTTP_SuccessProxiesUpstream` still green).

- [ ] **Step 8: Commit**

```bash
rtk git add agent-proxy/main.go agent-proxy/handler.go agent-proxy/handler_test.go
rtk git commit -m "feat(trace): extract/inject W3C context and tag conversation_id in agent-proxy"
```

---

### Task 5: Jaeger verification runbook

**Files:**
- Create: `docs/tracing-verification.md`

**Interfaces:**
- Consumes: the running docker-compose stack with Jaeger.
- Produces: a documented manual procedure; no code.

- [ ] **Step 1: Write the runbook**

Create `docs/tracing-verification.md` with:

```markdown
# Cross-service trace verification

## Purpose
Confirm trace propagation across Portal backend and agent-proxy, and determine
empirically whether OneChat forwards the W3C `traceparent` header.

## Steps
1. Bring up the stack: `rtk docker compose up -d` (includes Jaeger).
2. Send a chat request with a known trace id:
   ```bash
   curl -N http://localhost/api/v1/chat/stream \
     -H 'Content-Type: application/json' \
     -H 'traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01' \
     -d '{"query":"hello"}'
   ```
3. Open Jaeger UI (http://localhost:16686). Search by trace id
   `0af7651916cd43dd8448eb211c80319c`.

## Interpreting results
- **Single trace, all services present** (backend `chat_stream`, `onechat_call`,
  MCP span, `agent-proxy`): OneChat forwards `traceparent`. Goal fully met.
- **Multiple traces**: OneChat drops the header on its outbound calls. Fall back to
  correlation: in Jaeger, search by tag `conversation_id=<id from the done event>`
  to list every fragment across services.

## What each change guarantees
- Backend outbound always injects `traceparent` (Task 1).
- `/mcp` and agent-proxy always continue an inbound `traceparent` when present
  (Tasks 3, 4).
- Every service stamps `conversation_id`, so fragments are always joinable by tag
  (Tasks 2, 3, 4) regardless of OneChat's behavior.
```

- [ ] **Step 2: Commit**

```bash
rtk git add docs/tracing-verification.md
rtk git commit -m "docs(trace): add Jaeger cross-service verification runbook"
```

---

## Post-implementation

- [ ] Update `context.md` and commit (repo rule).
- [ ] Run full backend suite: `cd backend && rtk pytest` and agent-proxy: `cd agent-proxy && rtk go test ./...`.
- [ ] Open PR from `feat/otel-cross-service-trace`.
