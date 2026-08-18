# Clean Architecture assessment (deep, independent) — 2026-08-18

Independent re-audit of `backend/app` against **textbook Clean Architecture** (Uncle Bob's four
concentric layers + the Dependency Rule), gathered fresh with parallel read-only sweeps and
verified by direct read (`file:line`). It does **not** anchor to the prior
`assessment-methodology-compliance-2026-08-18.md`, which scored a pragmatic Active-Record target
and marked Clean Architecture "Partial → near-compliant". This one measures against the strict
model and reports what that lens sees.

**One-line verdict:** the **delivery boundary is clean** (routers hold no ORM, DTOs are
disciplined), but the **use-case and entity layers are not decoupled from frameworks** — there is
no repository/port abstraction anywhere, entities *are* the ORM, and infrastructure (Tortoise,
`httpx`, transactions, tracing, clock, config) is imported concretely inside use-cases. Plus **two
concrete dependency-rule breaks the prior audit missed.**

Rubric: (1) Dependency Rule, (2) Entity independence, (3) Use-case purity, (4) Interface adapters
/ ports, (5) Framework isolation, (6) Testability, (7) Boundary integrity.

---

## Scorecard

| Dimension | Verdict | Core issue |
|---|---|---|
| Dependency Rule | **2 breaks** | 1 service imports a router; 1 service imports FastAPI |
| Entity independence | **Fail (by design)** | Entities are Tortoise Active-Record `Model`s (anemic) |
| Use-case purity | **Weak** | Services call ORM/`httpx`/transactions/tracing concretely |
| Interface adapters / ports | **Absent** | No repository/gateway/port anywhere (1 unrelated Protocol) |
| Framework isolation | **Partial** | ORM leaks inward; FastAPI confined *except* 1 file |
| Testability | **Integration-only** | Use-cases need Tortoise+SQLite; no fake-repo seam |
| Boundary integrity | **Pass** | No ORM leaks across HTTP; clean request/response DTOs |

---

## What already holds (do not touch)

- **Routers build zero ORM querysets.** Verified: no `Model.filter/get/all/create` on any model
  class under `app/routers`. The `.get(`/`.create(` hits are decorators, dict access, or service
  calls (`routers/api_key.py:66` `api_key_service.create(...)`).
- **No ORM leaks across the HTTP boundary.** Every router returns a Pydantic DTO from
  `app/schemas` or a hand-built dict — never a raw `Model` instance
  (`routers/agencies/crud.py:89` `AgencyResponse.model_validate(...)`,
  `routers/users.py:43` `UserResponse.from_user(...)`, `routers/audit_log.py:35` `_row(a)`).
- **DTOs are clean.** Request/response split is textbook (`schemas/agency.py` →
  `AgencyCreate`/`AgencyUpdate`/`AgencyResponse`); schemas never subclass entities; explicit
  field-renaming translation where needed (`schemas/user.py:37` `from_user`, snake→camel).
- **Domain error vocabulary is framework-free.** `ApiError` (`app/errors.py:34`) is a plain
  `Exception`; FastAPI appears only in the handler-registration glue (correct delivery layer).
- **Dependency direction is otherwise correct.** No model imports `app.services`/`app.routers`
  (the one `models/llm_usage.py:11` hit is a comment). Routers → services → models holds.

The Phase-1 "strip FastAPI from services" refactor genuinely landed for **14 of 15** modules.

---

## Findings, ranked by (impact ÷ fix cost)

### TIER A — concrete Dependency-Rule breaks (small, mechanical, ship first)

**A1. A service imports a router (inner → outer inversion).** *Prior audit missed this.*
- `services/responses/session.py:93` — `WsSession._generate` (live: called at `:61`, wired from
  `routers/responses.py:33`) does `from app.routers.responses import run_response` and drives it.
  The use-case layer depends on the delivery layer.
- **Fix:** extract `run_response`'s body into a service function (e.g.
  `services/responses/run.py`), have the router *and* `WsSession` both call inward to it. ~1 file
  moved, no behavior change. **Cost: S.**

**A2. FastAPI in the service layer (last framework-in-service leak).** *Prior plan deferred this.*
- `services/responses/errors.py:7-8,34` — `from fastapi import FastAPI, Request` +
  `fastapi.responses.JSONResponse`; registers an exception handler. Registered live from
  `app/errors.py:67`.
- **Fix:** move the file to `app/` (delivery glue, next to `errors.py`) — it is handler
  registration, not a use-case. Import stays one line. **Cost: S.**

> After A1+A2, `grep -rE 'fastapi|app.routers' backend/app/services` is **zero** — the
> strict "no framework, no outward import in services" property actually holds.

### TIER B — the Active-Record core (large, structural, the real "not Clean Arch")

This is the tier the pragmatic audit **consciously tolerated**. It is the honest answer to "is
this Clean Architecture?": **no**, because the inner two rings depend on frameworks.

**B1. No repository / port abstraction exists — anywhere.**
- Searched all of `app` for `Protocol`/`ABC`/`abstractmethod` and `*repository/gateway/port/store/
  uow*`. The **only** inversion in the whole backend is `services/rate_limit.py:15`
  `class RateLimiter(Protocol)` — unrelated to persistence.
- Every use-case calls Tortoise concretely: `services/agency.py:33` `Agency.get(...)`,
  `:61` `Agency.create(...)`, `:107` `Agency.filter(...).update(F(...))`;
  `services/conversation.py:91` `Conversation.get_or_none(...)`;
  `services/user.py:41` `User.filter(...).count()`; `services/api_key.py:29` `UserAPIKey.create`;
  `services/message.py:18` `Message.get(...)`.
- ORM **exception vocabulary leaks inward** too: `tortoise.exceptions.DoesNotExist` imported in
  `services/conversation.py:6`, `user.py:13`, `message.py:5`.
- **Fix:** define `Repository` ports per aggregate (Protocols), implement Tortoise adapters, inject
  them into use-cases. **Cost: XL** (touches all 65 service files + wiring + tests).

**B2. Entities are anemic Active-Record models coupled to Tortoise.**
- All 16 models subclass `tortoise.models.Model` (`models/agency.py:21`, `conversation.py:7,41`,
  `user.py:7,35`, …). Business logic is almost entirely absent from entities — the only rules on a
  model are `User.is_admin` (`user.py:31`) and `UserAPIKey.is_usable()` (`user.py:48`). Everything
  else lives in service functions.
- **Fix (paired with B1):** introduce pure-Python domain entities (dataclasses) + mappers to/from
  ORM rows; move invariants onto entities. **Cost: XL.**

**B3. External gateways are concretely coupled; one mixes transport + persistence.**
- OneChat: `services/onechat/client.py:60` `OneChatClient` (concrete, no port); consumers import
  `get_client` directly (`services/chat/stream.py:30`, `services/session.py:4`). A `transport=`
  test seam exists but the type is the concrete class, not a port.
- LLM: `services/llm/client.py:119` `chat(...)` free function; consumers import it concretely
  (`services/chat/llm.py:21`, `services/agency.py:288`, …).
- **Transport + persistence mixed:** `services/llm/client.py:186` `_record_usage` does
  `LlmUsage.create(...)` **inside** the LLM transport client — a gateway writing to the DB.
- **Fix:** define `LlmGateway` / `OneChatGateway` ports; move usage-accounting out of the client
  into a use-case/consumer. **Cost: L.**

**B4. Transaction control + raw SQL leak into use-cases; no unit-of-work.**
- `tortoise.transactions.in_transaction` opened inside services: `services/chat/turn.py:51`,
  `services/feedback.py:60`, `services/analytics/dashboard.py:15`, `analytics/health.py:17`,
  `analytics/heatmap.py:20`, `analytics/brief.py:50`.
- Raw SQL over the connection inside a use-case: `services/feedback.py:61`
  `conn.execute_query("SET TIME ZONE ...")`; several analytics services run raw SQL likewise.
- **Fix:** a `UnitOfWork` seam owning transactions; push raw SQL into a query adapter. **Cost: L.**

### TIER C — cross-cutting infra embedded in use-cases (medium; do opportunistically)

**C1. Tracing interleaved with domain logic.** OpenTelemetry spans woven through business code:
`services/chat/stream.py:18-19,158-178`, `services/session.py` (nearly all span management),
`stream.py:33` `with_trace_query`. Clean Arch wants this as a decorator/adapter, not inline.
**Cost: M.**

**C2. Non-injected clock.** A global `now()` (`app/utils/__init__.py:15`) is called throughout
(`services/agency.py:183`, `feedback.py:80`, `chat/turn.py:55`, `analytics/health.py:28`, …).
Centralized (good) but not injectable — time can only be controlled by monkeypatch.
**Fix:** inject a `Clock` port. **Cost: M.**

**C3. Concrete `httpx` clients built inside use-cases.** `services/agency.py:144`,
`chat/dispatch.py:132`, `llm/client.py:138`, `agent_proxy.py:102`. Some allow a `transport=`
override (partial seam) but instantiate the client in-service. **Cost: M.**

**C4. Global config + module-level singletons as a de-facto container.** `from app.config import
settings` read globally in many services; process-global mutable state:
`services/llm/client.py:57,87,88`, `events.py:21`, `rate_limit.py:56`, `chat/stream.py:46`, plus
`usage_context` `ContextVar`s that `tests/conftest.py:27` must reset. Not IoC. **Cost: M–L.**

### TIER D — minor / contract hygiene (optional)

**D1. Routes without `response_model`** return bare dicts — no ORM leak, but weaker OpenAPI
contract: `routers/dashboard.py:18`, `routers/messages.py:14`, `routers/feedback.py:22`. **Cost: S.**

---

## Testability consequence (why B matters in practice)

Because use-cases call ORM classes directly with no port, **most service tests must boot Tortoise**
— `tests/conftest.py:14` inits in-memory SQLite + `generate_schemas()` for ~95 test files. Pure
unit tests exist only where logic is ORM-free (rate-limit math, spec parsing). The test seam is
"the ORM on SQLite", not an interface — so you cannot exercise a use-case with a fake repository.
Introducing ports (B1) is what would unlock true unit-level use-case tests.

---

## Decision menu (pick a scope; each is independently shippable)

1. **Tier A only** — fix the 2 real Dependency-Rule breaks (A1, A2). After this the strict "no
   framework / no outward import in the service layer" property genuinely holds. **~½ day, zero
   behavior change.** *Recommended baseline — do this regardless.*

2. **Tier A + selective C** — also inject a `Clock` (C2) and lift tracing to decorators (C1) for
   the highest testability-per-effort. **~2–3 days.**

3. **Tier A + B3/B4** — add gateway ports and a unit-of-work, un-mix transport/persistence in the
   LLM client. Real decoupling of *external* infra without rewriting the ORM story. **~1 week.**

4. **Full textbook (A + B1 + B2 + …)** — repository ports + pure entities + ORM adapters across all
   65 service files. This is the only path that makes the answer to "is this Clean Architecture?"
   an unqualified *yes*. **Multi-week, high risk, touches everything.** Weigh against the repo's
   standing YAGNI stance (CONTEXT.md) — the current Active-Record design is deliberate and works.

**Recommendation:** ship **(1)** now — it closes genuine violations cheaply. Treat **(3)** as the
next meaningful increment if decoupling is the goal. Only take **(4)** if strict Clean-Architecture
conformance is a hard product mandate that overrides the documented Active-Record/YAGNI decision;
it is a rewrite, not a refactor, and the delivery + DTO boundaries (which are already clean) are
not what would improve.
