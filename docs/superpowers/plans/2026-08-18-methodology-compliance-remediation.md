# Plan — Methodology-compliance remediation (2026-08-18)

> Source audit: `docs/assessment-methodology-compliance-2026-08-18.md`.
> Goal: close the concrete violations of the four mandated rules (Clean Architecture,
> full-English route names, 15-Factor, event-driven architecture) found by the full-read
> re-audit. TDD throughout (red → green → refactor); one workstream per `refactor/`/`chore/`
> branch; never commit multi-step work to `main`.

## Ordering rationale

Ship in strict-violation order, cheapest-safe-first inside each phase:

1. **Phase 1 — Clean Architecture** (clearest strict violation, mechanical, well-tested).
2. **Phase 2 — Route names** (3 renames; breaking, so isolated + parity-tested).
3. **Phase 3 — 15-Factor nits** (dead config removal; trivial, low risk).
4. **Phase 4 — EDA expansion** (optional; only if strict EDA compliance is wanted over the
   repo's documented YAGNI stance — decision gate below).

Each phase is independently shippable and independently revertible. Do **not** bundle phases.

---

## Phase 1 — Clean Architecture: remove the web framework from the service layer

**Violation.** 15 service modules import FastAPI, breaking the dependency rule inward
(use-case layer depends on the delivery mechanism):
- `HTTPException`/`status`: `services/agency.py`, `agency_golden.py`, `agency_lifecycle.py`,
  `agent_proxy.py`, `api_key.py`, `connection_log.py`, `conversation.py`, `feedback.py`,
  `llm/admin.py`, `message.py`, `popular_questions.py`, `user.py`.
- `BackgroundTasks`: `services/chat/stream.py`, `services/chat/aggregate.py`.

**Target.** Services raise **domain errors** and know nothing about HTTP or FastAPI scheduling.
Behavior (status codes, envelope, messages) stays byte-identical — the global handlers in
`app/errors.py` already produce the same envelope for `ApiError` and `HTTPException`, so this
is a pure structural refactor.

### Step 1.1 — extend the domain error vocabulary (enabling change, no behavior change)
- `app/errors.py`: add `ErrorCode.CONFLICT = "conflict"` and map `409: ErrorCode.CONFLICT` in
  `_STATUS_CODES` (today `llm/admin.py` raises `HTTPException(409)`; there is no 409 code yet).
- Test first: `tests/test_error_envelope.py` — assert `ApiError(ErrorCode.CONFLICT, "x", status=409)`
  yields `{"error":{"code":"conflict",...}}` with HTTP 409, and that a raw `HTTPException(409)`
  maps to the same envelope (back-compat during migration).

### Step 1.2 — migrate the exception-raising services (one file per commit)
For each of the 12 `HTTPException` modules, replace with `ApiError`:
- `HTTPException(404, "…")` → `raise ApiError(ErrorCode.NOT_FOUND, "…", status=404)`
- `HTTPException(400, "…")` → `ApiError(ErrorCode.INVALID_REQUEST, "…", status=400)`
- `HTTPException(403, "…")` → `ApiError(ErrorCode.FORBIDDEN, "…", status=403)`
- `HTTPException(409, "…")` → `ApiError(ErrorCode.CONFLICT, "…", status=409)`
- Drop `from fastapi import HTTPException, status`.
- **Keep the exact `detail` string** as the `ApiError` message (existing tests assert wording,
  e.g. "conformance", "in use by routes", "must be positive"). No message edits.
- TDD gate per file: the module's existing test suite must pass unchanged. Where a test asserts
  `pytest.raises(HTTPException)`, update it to `pytest.raises(ApiError)` and assert `.code`/`.status`
  in the **same commit** as the service change (red→green visible in one diff).

Commit order (leaf services first, so callers still compile):
`agency_golden` → `feedback` → `api_key` → `connection_log` → `message` → `conversation` →
`user` → `llm/admin` → `agency` → `agency_lifecycle` → `agent_proxy`.

### Step 1.3 — remove `BackgroundTasks` from `services/chat`
- Define a scheduling **port** in the service layer: a `Scheduler = Callable[[Coroutine], None]`
  alias (put it in `services/chat/stream.py` or a tiny `services/chat/ports.py`).
- `prepare_turn`/`run_turn`/`_schedule_classification` accept `schedule: Scheduler` instead of a
  concrete `BackgroundTasks | None`.
- Adapters live at the edges (already framework-aware):
  - HTTP router `routers/chat.py`: pass `lambda coro: background_tasks.add_task(_run, coro)`
    (or wrap `background_tasks.add_task`).
  - WS path (`services/chat/ws.py`) + `aggregate.collect_turn`: pass `spawn_logged`
    (`app/concurrency.py`) — it already does exactly this on the WS path today.
- Drop `from fastapi import BackgroundTasks` from `stream.py` and `aggregate.py`.
- TDD: existing `test_chat_*` and `test_aggregate.py` must pass; add one test asserting the
  injected `schedule` callback receives the classification coroutine.

### Phase 1 acceptance
- `grep -rE 'fastapi|HTTPException' backend/app/services` returns **zero** hits
  (`responses/errors.py` is the one legitimate framework-adjacent module — it registers the
  OpenAI handler; keep it, it is delivery-layer glue, or move it under `app/` — decide in review).
- Full backend suite green (currently ~852 pass / 6 skip); no route, status code, or envelope
  changed. `docker compose config` unaffected.

---

## Phase 2 — Full-English route names (3 renames)

**Violations** (short forms of ordinary words):
| Current | New | File |
|---|---|---|
| `GET /api/v1/dashboard/stats` | `/dashboard/statistics` | `routers/dashboard.py:14` |
| `GET /api/v1/feedback/stats` | `/feedback/statistics` | `routers/feedback.py:25` |
| `GET /api/v1/connection-logs/info` | `/connection-logs/information` | `routers/connection_logs.py:98` |
| `POST /api/v1/agencies/parse-spec` | `/agencies/parse-specification` | `routers/agencies/spec.py:29` |

**Exempt (do not touch):** OpenAI external contract (`/responses`, `/conversations`, `/items`,
`/input_tokens`, `/input_items`, `/compact`, `/cancel`), `/mcp/discover` (protocol proper noun),
`/api-keys` (API is the standard term). Documented in the audit.

### Steps (one rename per commit, breaking change → isolated)
Each rename is: backend route path **+** every frontend caller **+** tests, in one commit:
- Backend: change the decorator path; update the router/handler tests
  (`test_dashboard*`, `test_feedback_stats.py`, `test_connection_logs*`, `test_parse_spec*`)
  and `tests/test_surface_parity.py` (it walks the live route table).
- Frontend callers to update:
  - `dashboard/stats` → `features/dashboard/dashboardApi.ts`
  - `feedback/stats` → `features/chat/feedbackApi.ts` (shared with dashboard/feedback features)
  - `connection-logs/info` → `features/connection-logs/useConnectionLogs.ts`
  - `agencies/parse-spec` → the agency wizard spec-parse hook (`features/agencies/…` — grep
    `parse-spec` under `frontend/src`).
- Frontend tests: update MSW handlers in `src/mocks/handlers.ts` + any feature test asserting
  the URL.

### Phase 2 acceptance
- `grep -rnE '/stats"|/info"|parse-spec' backend/app/routers frontend/src` → only OpenAI-exempt
  hits remain (none of the four renamed paths).
- Backend suite + `tsc --noEmit -p tsconfig.app.json` + vitest all green.

---

## Phase 3 — 15-Factor nits (dead config removal)

Low-risk cleanup, can be one `chore/` branch, one commit each:
1. **Drop `python-jose`** from `backend/pyproject.toml` (JWT removed; the only mention in
   `backend/app` is the "JWT is gone" comment at `auth/dependencies.py:140`). Regenerate `uv.lock`
   (`uv lock`). Verify `app.main` imports + suite green.
2. **Remove dead JWT fields** from the frontend `RESTART_FIELDS`
   (`features/settings/SettingsPage.tsx:15` — drop `"JWT_SECRET"`, `"JWT_ALGORITHM"`; keep
   `DATABASE_URL`, `CORS_ORIGINS`). `tsc` + settings tests green.
3. *(Optional)* Fold the bootstrap `os.getenv("LOG_LEVEL")` at `main.py:23` — leave as-is unless
   the ordering can be untangled without importing `config` before logging is set up. Low value;
   default = skip and note it.

### Phase 3 acceptance
- `grep -rniE 'jose|jwt' backend/pyproject.toml frontend/src` → zero.
- Both suites green.

---

## Phase 4 — Event-Driven Architecture expansion (DECISION GATE — do not start without sign-off)

**Current state is a correct outbox seam, minimally used** (1 producer / 1 consumer; 17 direct
`record_audit`, 30 counter mutations, 4 `ConnectionLog` writes remain imperative). The repo has
**explicitly chosen YAGNI** here (CONTEXT.md: broker/consumers only when a second service needs
the stream).

**Gate:** strict "event-driven architecture methodology" compliance means domain state changes
emit events and side effects become consumers — a large, behavior-touching change. Only proceed
if the mandate is judged to override the documented YAGNI decision. **Default recommendation:
stop after Phase 3** and record the EDA seam as sufficient, OR do the single highest-value event
below and no more.

If proceeding, smallest meaningful increment (one event, TDD, additive — existing sync behavior
unchanged, new consumers run off the outbox):
1. `agency.call_completed` (payload: agency_id, status, latency, connection_type) published by
   the dispatch/proxy path → consumers: counter-increment projection + connection-log projection.
2. Then `message.rated` → counter + audit projections.
3. Then route every `record_audit` through an `audit.recorded` event.

Each is one publisher + one/two `subscribe`d consumers + `dispatch_pending` (already wired),
guarded by `tests/services/test_events.py`-style outbox tests. Stop when the mandate is satisfied.

---

## Cross-cutting discipline
- **TDD mandatory** every step (failing test first, confirm red, minimal green, refactor).
- **Branch per phase** (`refactor/clean-arch-service-errors`, `refactor/route-names-full-english`,
  `chore/dead-jwt-config`, `feat/eda-<event>`); PR into `main` (protected, PR-only).
- **After each phase:** update `CONTEXT.md`, commit; on merge to `main`, rebuild docker compose.
- **No behavior drift** in Phases 1–3: same routes (except the 3 deliberate renames), same status
  codes, same envelopes, same messages. Prove it with the existing suites, not by inspection.
