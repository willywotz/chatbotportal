# Backend feature slices — for an incremental Go port (2026-08-18)

This document cuts `backend/app` into **feature slices**. You port one slice at a time to Go.
Each slice lists its routes, services, models, external systems, and its coupling to other
slices. A recommended port order follows the coupling.

Written in Simplified Technical English.

Related: `docs/assessment-clean-architecture-2026-08-18.md` (why the port is a rewrite, not a
mechanical move — the use-cases are welded to the ORM, so no framework-free core carries over).

---

## How to run the port (strangler pattern)

You do **not** replace the backend in one step. You run Go and Python together and move one
slice at a time.

- **Caddy already path-routes** (`caddy/Caddyfile`). Add a rule that sends one route prefix to a
  new Go service; the rest stays on Python. Move prefixes as each Go slice passes its tests.
- **The database is the shared contract.** Both languages read the same Postgres schema (31 aerich
  migrations). Do not change the schema during a slice port. Keep the tables; change only the code
  that reads them. Freeze migrations on the Python side while a slice moves.
- **Parity gate per slice.** The slice is "done" in Go when it returns the **same HTTP status,
  same JSON envelope, and same body shape** as Python for the same input. Drive this with the
  existing Python test suite (165 test files) and `tests/test_surface_parity.py` as the contract.
- **bcrypt hashes carry over** — no credential migration. `pg_trgm`/`pgvector` are database-side,
  language-neutral.

---

## Shared kernel — port FIRST (every slice needs it)

This is not a feature. It is the base that all slices import. Build it in Go before slice 1.

| Concern | Python source | Go note |
|---|---|---|
| Config | `app/config.py` (pydantic-settings + DB overrides) | env struct + `Setting` table read; no Pydantic in Go — hand-write validation |
| Database | `app/database.py` (Tortoise init, aerich upgrade on start) | `pgx`/`sqlc`; keep schema; use `goose`/`golang-migrate` pointed at the same schema |
| Error envelope | `app/errors.py` (`ApiError`, `{"error":{code,message,retryable}}`) | one error type + middleware that writes the identical envelope |
| Domain events (outbox) | `services/events.py`, `event_consumers.py`, model `DomainEvent` | transactional outbox + a dispatch goroutine |
| Scheduler | `app/scheduler.py` (APScheduler + `dispatch_pending`) | `time.Ticker`/`robfig/cron` goroutines |
| Concurrency | `app/concurrency.py` (`spawn_logged`) | goroutine + recover + log |
| Request context | `services/usage_context.py` (ContextVars) | `context.Context` values |
| Log sanitize | `services/log_sanitize.py` | direct port |
| Tracing | `app/trace_util.py` + OTel | Go OTel SDK is first-class — near drop-in |
| Auth chokepoint | `app/auth/{dependencies,security,ws}.py` | middleware: API key + session cookie + role allowlist |

---

## The slices

Eight slices. Each is a portable unit. "Inbound" = who calls this slice; "Outbound" = what this
slice calls.

### Slice 1 — Identity & Access
Foundational. Every router reads the current user from here.

- **Routes:** `/authentication/*` (`routers/auth.py`), `/users/*` (`routers/users.py`),
  `/api-keys/*` (`routers/api_key.py`).
- **Services:** `auth_session.py`, `user.py`, `api_key.py`.
- **Models:** `User`, `UserAPIKey`, `Session`.
- **External:** bcrypt (password + API-key hashing).
- **Outbound:** kernel (auth, audit). **Inbound:** all other slices (via `get_current_user`).
- **Go risk:** Low. Standard CRUD + `x/crypto/bcrypt`. Hashes are portable.
- **Port:** with the kernel, first. Nothing else works without it.

### Slice 2 — Settings & admin config
- **Routes:** `/settings*` (`routers/settings.py`).
- **Services:** `settings.py`, `cache_flush.py`, `seed.py`.
- **Models:** `Setting`.
- **Outbound:** kernel (config override + cache flush). **Inbound:** config layer reads `Setting`.
- **Go risk:** Low. Key/value config with per-worker cache invalidation.
- **Port:** with the kernel — config depends on it.

### Slice 3 — LLM gateway (language-model routing)
The metering + routing layer for all LLM calls. Chat, agency spec-parse, and analytics briefs all
depend on it.

- **Routes:** `/language-model/*` (`routers/llm.py`).
- **Services:** `llm/{client,admin,purpose,seed}.py`, `rate_limit.py`, `usage_context.py`.
- **Models:** `LlmProvider`, `LlmRoute`, `LlmUsage`, `RateLimitCounter`.
- **External:** OpenRouter, ThaiLLM (both `httpx` → Go `net/http`).
- **Outbound:** kernel, rate limiter. **Inbound:** Chat, Agency (parse-spec), Analytics (brief).
- **Go risk:** Medium. **Note the audit finding:** the client mixes transport and persistence
  (`llm/client.py:186` writes `LlmUsage`). Split them in Go: a gateway that calls the provider, and
  a consumer/use-case that records usage.
- **Port:** third — before Chat and Agency, because they call it.

### Slice 4 — OneChat gateway (external adapter)
The transport client to the external OneChat orchestrator (v1–v5, sync + SSE).

- **Routes:** none (it is an adapter, not a surface).
- **Services:** `onechat/{client,__init__}.py`, `session.py` (session warm-up).
- **Models:** none.
- **External:** OneChat service (`ONECHAT_BASE_URL`), SSE + JSON.
- **Outbound:** kernel. **Inbound:** Chat.
- **Go risk:** Medium. SSE parsing + version adaptation. Go handles streaming well.
- **Port:** fourth — Chat needs it.

### Slice 5 — Chat pipeline (the core, largest)
The heaviest slice. Port its native part first, then the two OpenAI-compatible surfaces. All three
share one turn implementation.

- **Routes:**
  - Native: `/chat` (`routers/chat.py`), `/history/*` (`routers/conversations.py`),
    `/messages/{id}/rating` (`routers/messages.py`).
  - OpenAI Responses: `/responses/*` (`routers/responses.py`) — HTTP, SSE, **WebSocket**.
  - OpenAI Conversations: `/conversations/*` (`routers/openai_conversations.py`).
- **Services:** `chat/{stream,turn,llm,model,pipeline_snapshot,dispatch,aggregate,ws}.py`,
  `similarity.py`, `session.py`, `conversation.py`, `message.py`, `responses/*`, `openai/*`.
- **Models:** `Conversation`, `Message`.
- **External:** OneChat (slice 4), LLM classify (slice 3), MCP endpoint URL (callback), `pg_trgm`
  similarity cache.
- **Outbound:** slices 3, 4; writes `ConnectionLog`. **Inbound:** Agency conformance calls
  `chat/dispatch`.
- **Go risk:** **High.** Largest surface. The OpenAI Responses/Conversations wire format
  (streaming event types, WebSocket frames, keyset item pagination) must stay byte-compatible with
  the OpenAI SDK. `pg_trgm` similarity is DB-side (portable).
- **Audit fix to apply during the port:** `responses/session.py:93` imports the router
  (`run_response`) — a dependency inversion. In Go, put the run logic in the service and call
  inward from both the HTTP and WebSocket handlers.
- **Port:** fifth. Do native chat + history + rating, ship, then Responses, then Conversations.

### Slice 6 — Agency management
- **Routes:** `/agencies/*` — CRUD (`crud.py`), lifecycle/status/health
  (`lifecycle.py`), golden questions (`golden.py`), logo upload (`logo.py`),
  MCP discover + parse-specification (`spec.py`).
- **Services:** `agency.py`, `agency_golden.py`, `agency_health.py`, `agency_lifecycle.py`,
  `agency_reconcile.py`, `conformance.py`, `evaluation.py`, `mcp_discovery.py`.
- **Models:** `Agency`, `GoldenQuestion`, `EvalResult`.
- **External:** LLM parse-spec (slice 3), agency health probes (`httpx`), **local file volume for
  logos** (`UPLOAD_DIR` — the one 15-factor exception; plan S3/MinIO if you go multi-node in Go).
- **Outbound:** slice 3 (LLM), slice 5 (`conformance` → `chat/dispatch`), emits
  `agency.status_changed` event. **Inbound:** MCP slice, public-status read.
- **Go risk:** Medium. `conformance`/`evaluation` couple to the chat pipeline — port after slice 5.
- **Port:** sixth.

### Slice 7 — MCP server & agent proxy
Holds the **strongest lock**: FastMCP.

- **Routes:** `/mcp` (MCP protocol mount, `app/mcp/server.py`),
  `/agent-proxy/{agency_id}` (`routers/agent_proxy.py`).
- **Services:** `app/mcp/{server,client}.py`, `agent_proxy.py`.
- **Models:** reads `Agency` (slice 6), writes `ConnectionLog`.
- **External:** OneChat calls **into** `/mcp` and through `/agent-proxy`; the proxy streams to
  agency `endpoint_url`.
- **Go risk:** **High — evaluate before committing.** `fastmcp>=2.3.0` (tools, resources,
  middleware, `CurrentContext`) has **no equal-maturity Go library**. Options: `mark3labs/mcp-go`
  or the official Go MCP SDK — both younger. `agent-proxy` alone is easy (a streaming reverse
  proxy — it was Go until yesterday). **Recommendation: keep `/mcp` on Python longest** (strangler)
  and port `/agent-proxy` early with slice 6 if you want.
- **Port:** last, or split — proxy early, MCP server after a Go-MCP spike.

### Slice 8 — Analytics & insights (read-heavy, low risk)
Reporting over data the other slices write. Mostly raw SQL.

- **Routes:** `/dashboard/statistics`, `/insight/*` + `/analytics-insights` + `/agency-health` +
  `/usage-heatmap`, `/executive-summary*`, `/feedback/*`, `/connection-logs/*`,
  `/public/popular-questions` + admin popular-questions, `/audit-log/*`, `/public/*`.
- **Services:** `analytics/{dashboard,health,heatmap,brief}.py`, `feedback.py`,
  `connection_log.py`, `popular_questions.py`, `audit.py`, `public_status.py`.
- **Models:** `ConnectionLog`, `ExecutiveBrief`, `PopularQuestion`, `AuditLog`, `LlmUsage`.
- **External:** LLM (executive brief, slice 3), raw SQL (`SET TIME ZONE`, aggregates).
- **Outbound:** reads many tables; `audit.py` is the **event consumer** (audit projection).
- **Go risk:** Low–Medium. No live behavior, read-only surfaces. But the queries span many tables —
  port after the slices that own those tables, so the schema is stable.
- **Port:** last (with, or after, slice 7). Safe to leave on Python indefinitely.

---

## Cross-cutting tables (do not let a slice "own" these alone)

Two tables are written by several slices. Keep their write path identical in both languages until
every writer has moved.

- **`ConnectionLog`** — written by Chat (slice 5), Agent-proxy (slice 7); read by Analytics
  (slice 8). Port readers only after all writers agree on the row shape.
- **`AuditLog`** — written through the audit service by many slices; also an **event consumer**.
  Route all audit writes through the same outbox event in Go so the projection stays single-source.

---

## Recommended port order

```
0. Shared kernel  (config, db, errors, outbox, scheduler, auth)   ── base
1. Identity & Access                                              ── every route needs current-user
2. Settings                                                        ── config overrides
3. LLM gateway                                                     ── chat + agency + analytics need it
4. OneChat gateway                                                 ── chat needs it
5. Chat pipeline   (native → Responses → Conversations)            ── the core
6. Agency management                                               ── conformance needs chat (5)
7. MCP + agent-proxy   (proxy early optional; MCP after a Go spike)── the FastMCP lock
8. Analytics & insights                                            ── read-only, port last
```

Each arrow-level down depends on the levels above it. You can ship after any level and route that
prefix through Caddy to Go while the rest stays on Python.

## Before slice 1 — de-risk the lock

Do a **spike** on the FastMCP replacement (slice 7) before you commit to a full Go program. If no
Go MCP library meets your needs, the plan changes: keep `/mcp` on Python permanently and port the
other seven slices. That single answer decides whether this is a full migration or a partial one.
