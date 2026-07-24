# LLM Route Test Buttons — Design

Date: 2026-07-25
Status: Approved

## Goal

Let an admin verify each LLM route works end-to-end from the `/settings/llm` Routes
panel. Today routes can only be edited; there is no way to fire a real request through
one. Agencies have a "test connection" feature; LLM routes have nothing. This adds a
per-route **Test** button plus a **Test all** button that run a real minimal completion
through the route and report success + latency (or the error).

## Scope

There are 5 purposes (`classification`, `brief`, `judge`, `parse_spec`,
`popular_questions`), each mapped to exactly one `LlmRoute`.

- Per-route **Test** button in `LlmRoutesList`.
- **Test all** button in the `RoutesPanel` header (runs all 5 in parallel).
- Result badge: **✓ <latency>ms** on success, **✗ <error>** on failure.

Out of scope: testing disabled routes, streaming, cost display, per-purpose realistic
prompts. (See decision below.)

## Backend

### Endpoint

`POST /api/v1/llm/routes/{purpose}/test` in `backend/app/routers/llm.py`, admin-only
(`require_admin`, consistent with the rest of the router).

- `purpose` not in `KNOWN_PURPOSES` → `404`.
- Always returns `200` with the result body; failures ride in `ok: false` so the
  frontend has a single happy path.
- No audit entry (a test is not a mutation).

### Result schema

`LlmRouteTestResult` in `backend/app/schemas/llm_route.py`:

```
ok: bool
latency_ms: int
model: str | None      # resolved model when the route resolved
error: str | None      # human-readable message on failure
```

### Service

Add `async def ping(purpose: str) -> LlmRouteTestResult`-shaped result to
`backend/app/services/llm/client.py`, re-exported from `app/services/llm/__init__.py`.

- Reuses the existing `chat()` production path for a faithful end-to-end check
  (resolution, auth, rate-limit, usage recording all exercised).
- Sends `messages=[{"role": "user", "content": "ping"}]`.
- Adds a new optional `max_tokens: int | None = None` param to `chat()` (passed through
  to the request body) so the ping caps output at `max_tokens=1`, keeping cost to a
  token or two.
- Wraps the call: measure latency with `time.monotonic()`; on success
  `{ok: True, latency_ms, model: result.usage.model}`; on `LlmError`
  `{ok: False, latency_ms, model: None, error: str(exc)}`.

### Decision: enabled-only, faithful path

The test resolves via the production path, which selects **enabled routes and providers
only**. Testing a disabled route/provider returns a clear failure ("no enabled route" /
"provider disabled") rather than testing it anyway. Rationale: simplest, and faithful to
what production would do.

### Decision: Test all runs in parallel

The frontend fires all 5 tests concurrently. Provider rate-limit queues already guard
the backend, so 5 simultaneous pings are safe.

## Frontend

- `frontend/src/features/llm-routes/llmRouteApi.ts`: add
  `testRoute(purpose: string): Promise<LlmRouteTestResult>` → POST the endpoint above.
- `frontend/src/features/llm-routes/LlmRoutesList.tsx`: per-card **ทดสอบ** button and a
  result badge; local state keyed by purpose: `idle | testing | done`, holding the last
  result. Spinner while `testing`.
- `frontend/src/features/llm-routes/RoutesPanel.tsx`: header **ทดสอบทั้งหมด** button that
  triggers a test for every purpose in parallel and fills each card's badge; disabled
  while any test is in flight.
- Match the existing agency "test connection" UI style (shadcn `Button` + spinner).

## Data flow

click → `POST /llm/routes/{purpose}/test` → resolve enabled route → 1-token ping →
`{ok, latency_ms, model, error}` → badge.

## Tests (TDD)

Backend (`backend/tests`, following existing `/llm` router tests):

1. Success — mocked provider returns 200 → `ok: true`, `latency_ms >= 0`, `model` set.
2. Disabled route → `ok: false`, config error in `error`.
3. Unknown purpose → `404`.

Frontend (following existing component-test patterns):

4. `LlmRoutesList` shows a ✓ badge after a mocked `testRoute` resolves; ✗ on reject.
