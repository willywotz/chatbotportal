# Lean and De-couple the Backend — Design

- Date: 2026-08-18
- Status: Draft for review
- Scope: Python backend (`backend/app`). The `backend-go/` port is out of scope.
- Language of prose: ASD-STE100 Simplified Technical English.

## 1. Purpose

Make the backend smaller and less coupled. Two goals:

1. **Lean** — delete dead and unused code.
2. **De-couple** — remove the three coupling problems that the Clean
   Architecture audit found.

This document is the agreed design. A separate implementation plan comes
after you approve this document.

## 2. Decisions locked (from the requester)

- **Lean means: remove dead/unused features.** (Not "trim one area", not
  "keep all features".)
- **De-couple all three problems, ranked by me.**
- **Delivery: one design doc first**, then step-by-step execution.
- **The OpenAI-compatible API surface: DELETE both** (`/conversations`
  OpenAI router and `/responses` router, with their service packages).
  Evidence showed no internal caller and no frontend caller.

## 3. Evidence base

Two read-only scouts read the current code on 2026-08-18.

- The service layer is well-connected. The graph found **no orphan
  helper/service functions**. Genuine dead code is small.
- The OpenAI-compatible surface has **no internal caller and no frontend
  caller**. It is only reachable from outside through Caddy.
- All three coupling problems are **CONFIRMED** in the current code.

> Note: the codebase-memory graph was not indexed at scout time for the
> coupling scan; that scout used Grep/Read directly. The dead-code scout
> indexed `backend/` (2668 nodes / 17475 edges).

## 4. Part A — Lean (delete dead code)

### A0. Trivial dead code (HIGH confidence)

Delete now. No behavior change.

| Item | Location | Evidence |
|---|---|---|
| `OneChatClient.stream_v4` | `backend/app/services/onechat/client.py:116-120` | Zero callers. Live path is `events()`. |
| `OneChatClient.stream_v5` | `backend/app/services/onechat/client.py:122-126` | Zero production callers. |
| Its isolated test | `backend/tests/services/onechat/test_client_stream.py` (the `stream_v5` cases) | Tests only the dead method. |
| Stale comment `app.main:app` | `backend/pyproject.toml:48` | Entrypoint is now `asgi_app`. |

### A1. Delete the OpenAI-compatible API surface (largest lean win)

This is the biggest removable slice. It also erases parts of the coupling
problems (see Part B). Delete these files/blocks in full:

**Routers**
- `backend/app/routers/openai_conversations.py` (prefix `/conversations`)
- `backend/app/routers/responses.py` (prefix `/responses`, HTTP + WebSocket)

> KEEP `backend/app/routers/conversations.py` — that is the native
> `/history` router. It stays.

**Service packages (delete the whole directory)**
- `backend/app/services/openai/` — `conversations.py`, `identity.py`,
  `ids.py`, `items.py`, `metadata.py`, `__init__.py`
- `backend/app/services/responses/` — `continuity.py`, `errors.py`,
  `request.py`, `retrieve.py`, `session.py`, `translate.py`, `__init__.py`

**Glue edits (the only touch-points outside the deleted packages)**
- `backend/app/main.py:48-49` — remove the two router imports.
- `backend/app/main.py:145-146` — remove the two `include_router` lines.
- `backend/app/errors.py:67-69` — remove the import and the
  `register_responses_error_handler(app)` call.
- `backend/app/config.py:80-81` — remove `RESPONSES_WS_MAX_CONNECTIONS`
  and `RESPONSES_WS_MAX_DURATION_SECONDS` (dead after deletion).
- `caddy/Caddyfile:26-38` — remove the `@api_responses` block and its
  comment. After removal, `/api/v1/responses` falls through to the general
  `@backend` matcher and returns 404, which is correct.

**Tests to delete with the code**
- `backend/tests/services/test_openai_*.py`
  (conversations, ids, identity, items, metadata)
- `backend/tests/services/test_responses_*.py`
  (retrieve, request, translate, ws_session, continuity)
- `backend/tests/routers/test_responses_http.py`
- `backend/tests/routers/test_responses_ws_route.py`

**Test that needs care — do not just delete**
- `backend/tests/services/test_soft_delete_filter.py` imports
  `app.services.responses.continuity` and `.errors`. One case
  (`test_get_messages_404s_for_soft_deleted_conversation`) checks core
  soft-delete behavior for messages. Keep that behavior under test:
  rewrite the case to exercise the native message/history path, not the
  deleted `responses` path. The other case
  (`test_continuity_ignores_soft_deleted_assistant_message`) is
  responses-only — delete it.

### A2. Low confidence — leave for now (YAGNI)

- `backend/app/mcp/client.py` (`main`) — a standalone MCP CLI utility. Not
  wired into compose or entrypoint. Keep unless you want to prune dev
  tools. Out of scope for this design.

## 5. Part B — De-couple (ranked)

The three problems are ranked by cost. The rank changes because Part A1
deletes code first. **We do not de-couple code that we delete.**

### How the deletion shrinks the work

- **P2 openai⇄responses cycle: GONE.** Both sides are deleted.
- **P3 (a) router-import leak and (c) WebSocket inversion: GONE.** Both
  live in `services/responses/session.py`, which is deleted.
- **P3 second dependency break (FastAPI in the service layer): GONE.** It
  is in `services/responses/errors.py`, which is deleted.

So after Part A, only the items below remain.

### P3 — Delivery-layer leaks (cheapest, do first)

After deletion, only one leak remains:

- **LLM gateway mixes transport with persistence.**
  `backend/app/services/llm/client.py:186-190` — `_record_usage` does
  `await LlmUsage.create(...)` inside the transport client. The client
  both calls the model and writes usage rows.
  - **Fix:** the `chat()` method returns usage data. A caller (a use-case
    service) writes the usage row. The gateway does transport only.
  - **Blast radius:** `client.py` plus its `chat()` callers
    (`chat/llm.py`, `agency.py`, `popular_questions.py`, analytics).
    Small-to-medium.

### P2 — Cross-feature coupling (middle)

After deletion, the entangled clusters shrink to:

- **`chat/stream.py` hub** — it imports models and services from other
  features: `ConnectionLog`, `Conversation`, `Message`, `User`, plus
  `onechat`, `session`, `similarity`, `log_sanitize`. This is the widest
  fan-out that remains.
- **`llm` magnet** — imported by `chat`, `agency`, `evaluation`,
  `popular_questions`, `analytics`.

**Approach (design intent, details in the plan):**
- Give `chat/stream.py` a narrow input contract (a small set of
  parameters or one dataclass) so it does not reach into four other
  features directly. Move cross-aggregate reads behind the seam that P1
  introduces (see below), so `stream.py` depends on ports, not on other
  features' ORM models.
- The `llm` magnet is acceptable as a shared kernel service if its
  interface is narrow and stable. Confirm its public surface; do not try
  to remove a shared dependency that is correctly shared.

**YAGNI:** do not break every one of the ~57 intra-service edges. Target
only the hub (`chat/stream.py`) and any true two-way cycle. A shared,
one-way dependency on a stable service is fine.

### P1 — ORM coupling (costliest, do last, incremental)

- **Problem:** no repository/port seam exists. ~37–43 service files import
  Tortoise models directly. ~140 ORM call sites. ORM exceptions
  (`tortoise.exceptions.DoesNotExist`) leak into services.
- **Approach:** introduce repository ports **one aggregate at a time**.
  Start with the highest-traffic aggregates that the scouts named:
  `Message` (33 call sites), `Agency` (19), `Conversation` (15),
  `User` (12). For each aggregate:
  1. Define a port (a `Protocol`) for the operations that services use.
  2. Write a Tortoise-backed adapter that implements the port.
  3. Route services through the port. Translate ORM exceptions at the
     adapter boundary so they do not leak inward.
  4. Keep tests green at each step (TDD).
- **Rule:** one aggregate per branch. Never convert all 140 sites at once.
- **Blast radius:** XL overall, but bounded per aggregate.

**YAGNI:** do not build a full Unit-of-Work or a generic repository base
class up front. Add only the port methods that real callers use. Add a
UoW only when a real multi-write transaction needs one.

## 6. Sequencing (branch per phase, TDD)

Each phase is its own branch. Merge only when green. Follow the mandated
TDD loop for every code change.

1. **Phase L0** — A0 trivial deletions. Branch `chore/dead-onechat-stream`.
2. **Phase L1** — A1 delete the OpenAI surface. Branch
   `refactor/remove-openai-surface`. This is the big lean step. Run the
   full test suite; confirm the count drops by the deleted tests only and
   the rest stay green.
3. **Phase D1 (P3)** — move LLM usage persistence out of the gateway.
   Branch `refactor/llm-gateway-transport-only`.
4. **Phase D2 (P2)** — narrow the `chat/stream.py` contract. Branch
   `refactor/chat-stream-decouple`.
5. **Phase D3 (P1)** — repository ports, one aggregate per branch:
   `refactor/repo-port-message`, `-agency`, `-conversation`, `-user`, …

After each phase: update `CONTEXT.md` and commit (per project rule).

## 7. Verification checklist

- After L1: `grep -rE 'services\.(openai|responses)|routers\.(responses|openai_conversations)' backend/app`
  returns nothing.
- After L1: no import of `run_response`, `register_responses_error_handler`,
  or `RESPONSES_WS_*` remains.
- After each phase: full backend test suite green.
- After D1: `grep -n 'LlmUsage' backend/app/services/llm/client.py` returns
  nothing.
- After each D3 aggregate: no direct `from app.models import <Aggregate>`
  in that aggregate's service files; only the adapter imports the model.

## 8. Out of scope

- The `backend-go/` port.
- `app/mcp/client.py` CLI utility.
- General refactors not tied to these two goals (for example the duplicate
  `_run_coro` helper in `routers/chat.py` and `routers/responses.py` — the
  latter is deleted in L1, which removes the duplication for free).

## 9. Open items to confirm

- **Data:** deleting the OpenAI surface removes HTTP routes only. It does
  not drop any table. Confirm no separate ops client depends on
  `/api/v1/responses` or `/api/v1/conversations` before L1 merges to a
  deployed environment. (Requester chose "delete both"; this is a
  deploy-time safety check, not a code blocker.)
- **P2 scope:** confirm the final list of `chat/stream.py` edges to cut
  after L1, since some edges vanish with the deletion.
