# Project Context — AI Chatbot Portal (Thai Citizen Guide)

> Primary orientation doc for this repo. Loaded into every session via `CLAUDE.md` (`@context.md`).
> Keep it current: **after any completed code change, update this file, commit, and (on merge to `main`) rebuild docker compose.**

## What this is

An **AI gateway / one-stop-service portal** that routes Thai citizens' natural-language
questions to the relevant Thai government agencies and returns a synthesized answer.
Product-facing name has been rebranded **"AI Chatbot Portal"** (backend `APP_NAME`, frontend UI);
the repo and `README.md` still carry the original **"Thai Citizen Guide"** name.

A citizen asks a question → the orchestrator decomposes it into sub-questions →
dispatches them to matching agencies over **API / MCP / A2A** → synthesizes the
agency responses into one LLM-written answer with citations. An admin dashboard
manages agencies, health, analytics, users/roles, API keys, and LLM routing.

The heavy orchestration (decompose → route → dispatch → synthesize, sync **v1–v3** and
streaming **v4/v5**) runs in an **external OneChat service** (`ONECHAT_BASE_URL`, reached via the
`services/onechat/` client).
This backend is the **portal/gateway**: it wraps OneChat, exposes its own MCP server of
agency data that OneChat calls back into, persists conversations, and provides all the
admin/analytics/auth surface.

## Services (docker-compose.yaml)

All traffic enters through **nginx** on one port; services talk over the `chatbot-network`.

| Service | Tech | Role |
|---|---|---|
| **nginx** | nginx | Reverse proxy. HTTP on `EXTERNAL_HTTP_PORT`, TLS on `EXTERNAL_HTTPS_PORT`. Routing in `nginx/routes.conf`. |
| **backend** | Python 3.12 · FastAPI · Tortoise ORM · FastMCP | REST API (`/api/v1`), MCP server (`/mcp`), scheduler, auth. Port 8080. |
| **agent-proxy** | Go 1.26 · pgx · OTel | Reverse-proxy from backend → agency endpoints; logs connection attempts. Port 8080. |
| **frontend** | React 18 · Vite 5 · TS · shadcn/ui | SPA admin + public portal. Port 8080. |
| **postgres** | pgvector/pgvector:pg16 | Shared DB (backend + agent-proxy). Extensions: `pg_trgm`, `fuzzystrmatch`, `vector` (created by `postgres-init`). |
| **redis** | redis:7-alpine | Shared LLM-provider throttle budget across workers (optional; empty `REDIS_URL` = in-process limiter). |
| **jaeger** | jaegertracing/jaeger:2.18.0 | OTLP tracing sink (`jaeger:4317`), UI proxied at `/jaeger/`. |
| **certbot** | certbot/certbot | Renews the Let's Encrypt cert every 12h over the HTTP-01 webroot. No-op until one is issued. |

**nginx routing (`nginx/routes.conf`, single source of truth):**
- `/api`, `/sse`, `/messages`, `/mcp`, `/docs`, `/redoc`, `/openapi.json` → `backend:8080`
  (`/api/v1/responses` also serves a **WebSocket**: an exact-match location adds the
  `$connection_upgrade` map and a 3700s read timeout, since the app holds sockets for up to
  60 min — the shared 300s timeout would kill an idle one long before the cap.)
- `/agent-proxy/` → `agent-proxy:8080`
- `/jaeger/` → `jaeger:16686`
- `/` (everything else) → `frontend:8080` (SPA)

`nginx/routes.conf` is included by both the HTTP server (`nginx/default.conf`, :8080) and the TLS server
(`nginx/tls.conf.template`, :8443) so the two can never drift.

**TLS (`docs/tls.md`)** is opt-in via `CERT_DOMAIN` (prod: `chatbotportal.opdc.ai.in.th`) and
self-enabling: `nginx/tls.sh` runs from the image's `/docker-entrypoint.d/` and writes the TLS
server block plus an HTTPS redirect **only once a cert exists**, so nginx never fails to start on
a missing certificate and local dev stays plain HTTP. It then watches hourly and reloads on
issuance/renewal. `/.well-known/acme-challenge/` is served from the `acme-challenge` volume the
certbot container writes to, and is the one path exempt from the redirect. First issuance is a
one-off `certbot certonly` — see `docs/tls.md`.

`docker-compose.override.yaml` adds dev watch/rebuild rules per service, plus the dev tunnel below.

**Dev tunnel (`docker-compose.override.yaml`, dev only — never deployed).** `cloudflared` runs an
always-on Cloudflare **Quick Tunnel** to `nginx:8080`, publishing the whole gateway on a random
`https://<words>.trycloudflare.com` URL for sharing a running dev stack. Outbound-only, so no port
is published and no Cloudflare account or DNS record is involved; TLS terminates at Cloudflare and
nginx still serves plain HTTP. The hostname is **random per restart**, so it is read back at
runtime from cloudflared's metrics server (`--metrics 0.0.0.0:2000`, container-internal) rather
than configured: `scripts/tunnel-url.sh` polls `/quicktunnel` and prints the URL, and the one-shot
`tunnel-url` sidecar runs it at startup. Re-print on demand with
`docker compose run --rm --no-deps tunnel-url` (`--no-deps` — otherwise Compose restarts
`cloudflared` and changes the URL you asked for).

Both tunnel images track **`latest` on purpose**: services in `docker-compose.yaml` stay pinned
because they ship, but dev-override services do not, and `cloudflared` in particular is a client of
a moving remote service whose old clients Cloudflare deprecates server-side. Trade-off: `up` does
not re-pull, so machines drift — `docker compose pull cloudflared` when it misbehaves.

⚠️ **The tunnel URL is public and unauthenticated.** The sharpest consequence is billable, not
informational: `/api/v1/chat` and `/api/v1/chat/stream` use `get_current_user_optional`
(`app/routers/chat.py`), so **anonymous callers can drive the LLM on your `OPENROUTER_API_KEY`** —
a leaked link means someone else's traffic on your balance. They are also **unthrottled**: there is
no per-user rate limit or spend quota, so a leaked link's traffic is bounded only by whatever spend
cap you set on the OpenRouter key. It also exposes the read-only surface
(`/jaeger`, `/docs`, `/redoc`, `/openapi.json`). Random and unguessable is not access control; keep
a spend cap on the OpenRouter key and rotate it if a link escapes. See `docs/quickstart.md`
§ "Sharing a dev environment".

`frontend/vite.config.ts` sets `server.allowedHosts: [".trycloudflare.com"]` — **required**, since
Vite 5.4.12+ rejects unknown Host headers; without it every tunnelled request returns
`Blocked request`. Leading dot = domain-suffix match, so it survives the hostname changing.

## Request flow (chat)

`POST /api/v1/chat` (sync) and `POST /api/v1/chat/stream` (SSE) live in
`backend/app/routers/chat.py`.

1. **Similarity cache** (new conversations only): `services/similarity.py`
   `find_similar_question()` uses **`pg_trgm`** trigram similarity (`SIMILARITY_THRESHOLD` 0.95,
   `SIMILARITY_WINDOW_SECONDS` 3 days) over prior successful turns. Hit → copy cached answer
   (no new ConnectionLog, so copies never re-cache). Vector embeddings were removed in favor of
   `pg_trgm` (migration `19_..._drop_embedding_add_pg_trgm`); the `vector` extension is installed
   but not currently used for chat similarity. Note: `Conversation.status="failed"` is a one-way
   ratchet, so failed turns never poison the cache.
2. **Dispatch to OneChat** via the transport client `services/onechat/` (`get_client(version)` →
   `OneChatClient`): sync `/chat` → `chat_external()` calls `chat_v3()`; `/chat/stream` and the
   Responses API drive `client.events()`, which serves any upstream version uniformly — v4/v5 stream
   SSE, v1/v2/v3 POST one JSON envelope adapted into `answer`+`done` (spec/api/v3.md: v3 `data`
   equals the streaming `answer` payload). The version comes from `resolve_version()`
   (`services/onechat/client.py`): a per-request override wins, else the newest version (`v5`); the
   `_STREAMS_SSE` table is the single source of truth for the version roster and each version's
   transport. `CHAT_STREAM_VERSION` was removed — `/chat/stream` has no per-request channel, so it
   always uses newest. Re-emits `answer`/`error`/`done` events.
   The client owns transport only (payload, HTTP/SSE, error mapping: non-200→status,
   `ReadTimeout`→504, other→502); persistence/tracing stay in the callers. All paths derive from a
   single `ONECHAT_BASE_URL` (the old per-endpoint `ONECHAT_V3/V4/V5_URL` settings are gone). **v5** (`spec/v5.md`) adds a `summarize` step event
   plus `summary`, `references[]` (citations scoped to the summary only — `sections[]` stay raw)
   and `thread_name`; when upstream summary generation fails it degrades silently to output
   identical to v4. Payload includes `mcp_endpoint_url` so OneChat can call back into agency MCP
   tools. Existing conversations first do `ensure_session_warmed()` (`services/session.py`).
3. **Persist**: `services/chat/turn.py::save_turn()` writes Conversation + user/assistant
   Messages + a `ConnectionLog` (action=`query`). On a v5 turn the assistant Message also stores
   `summary`/`summary_references`, and a non-null `thread_name` titles the conversation — but only
   on the turn that creates it, so the thread is never renamed mid-conversation.
4. **Classify** (background task): `services/chat/llm.py::classify_message_category()` tags the
   turn with a Thai category via the classification LLM.

`POST /api/v1/responses` is an **OpenAI Responses API compatible** surface over the same
pipeline (`routers/responses.py`), in three transports: HTTP non-streaming, HTTP SSE, and a
WebSocket on the same path. It shares one turn implementation with `/chat/stream` via
`services/chat/stream.py` (`prepare_turn` / `run_turn`), and translates to OpenAI's wire
format in `services/responses/`. The only model id is `onechat` (anything else → 400); callers
select the OneChat upstream per request with the `onechat_version` body field (`v1`–`v5`, else
newest) — a body field, not a header, so it works over WebSocket, which cannot set headers. `store` is accepted but ignored, `usage` is always zero, and
pipeline progress events are not surfaced. Response **creation, retrieval (`GET /responses/{id}`,
reconstructed from the stored assistant `Message` in `services/responses/retrieve.py`), soft
delete, and input-item listing** are implemented; `cancel`/`compact`/`input_tokens` are registered
`501 not_implemented` stubs. **The entire OpenAI Conversations + items API is implemented** in
`routers/openai_conversations.py` (create/get/update/delete + items create/list/retrieve/delete,
backed by the `Conversation`/`Message` store, `conv_`/`msg_` ids, keyset item pagination). Both
surfaces enforce **ephemeral temp-user ownership** (`services/openai/identity.py`: anonymous
callers get a minted temp `User` + JWT returned via the `X-Portal-Session` header; every read/delete
checks `owns()` → 404, never 403) and **soft delete** (`deleted_at`, filtered from all reads). Full
contract: `spec/openai-responses-extended.md`; base tables in `spec/openai-responses.md`.
Streaming is still a subset: the upstream declares 53 event
types (`spec/openai-responses-api/4-streaming-events.md`) but the module emits only **9** (the
8-event happy path plus `response.failed`); the other 44 — tools, reasoning, audio, image gen,
MCP, code interpreter, refusals, background/queued lifecycle — are out of scope (§ 5.1 "Event
scope"). The WebSocket reference (`spec/openai-responses-api/5-websocket-events.md`) declares
1 client event + those same 53 server events; the WS transport implements the 1 client event
(`response.create` only) and emits the same 9 server events, so § 8.1 states the 1/1 + 9/53 gap
(the upstream `error` server event is out of scope — the portal's `error` frame is its own
shape). The native SPA history router (`routers/conversations.py`) moved from
`/api/v1/conversations` to **`/api/v1/history`** to free the former path for the OpenAI
Conversations surface; it is a different contract — not a partial OpenAI Conversations
implementation.

In-process agency dispatch (API/MCP/A2A) also exists in `services/chat/dispatch.py`
(retry/backoff, per-agency timeouts) — used for the direct-orchestration path.

## Backend (`backend/`)

FastAPI app wired in `app/main.py`; config in `app/config.py` (pydantic-settings
`Settings`, plus DB-persisted overrides via the `Setting` model & `/settings` page).
Lifespan runs: assert prod secrets → init DB → load DB settings → seed admin & agencies →
start scheduler → mount MCP. `uvicorn --workers 4` in prod, so MCP runs **stateless-http**.

**Package map (`app/`):**
- `routers/` — 18 mounted REST routers, all mounted under `/api/v1`: `auth`, `users`, `agencies/`
  (package: `crud`, `golden`, `lifecycle`, `logo`, `spec`, `_utils`), `conversations`, `messages`,
  `chat`, `dashboard`, `feedback`, `connection_logs`, `api_key`, `executive_summary`,
  `insight`, `public_status`, `popular_questions`, `settings`, `audit_log`, `llm`, `responses`.
  (`seed` router is not mounted.) `popular_questions` exposes anonymous
  `GET /public/popular-questions` + admin CRUD `/popular-questions` + `POST …/regenerate` (202).
  `public_status` also exposes anonymous `GET /public/agencies` — a display-safe agency directory
  (id/name/short_name/logo/description/connection_type/status, non-draft only; no internals) that
  feeds the portal's หน่วยงานที่เชื่อมต่อ block.
- `models/` — Tortoise ORM (see Data model).
- `schemas/` — Pydantic request/response models.
- `services/` — domain logic: `agency*` (health, lifecycle, reconcile, conformance),
  `chat/` (dispatch, llm, turn, **`stream`** — the transport-free turn pipeline shared by
  `/chat/stream` and `/responses`), `responses/` (request mapping, continuity, event
  translation, WebSocket session), `analytics/` (brief, dashboard, health), `similarity`,
  `rate_limit` (LLM-provider throttle only), `session`, `evaluation`, `mcp_discovery`,
  `usage_context`, `log_sanitize`, `audit`, `cache_flush`, `user`.
- `auth/` — `security.py` (bcrypt, JWT, API-key hashing) and `dependencies.py` (the **sole**
  authz module: dual-token resolution + the RBAC chokepoint). The former `authz.py` ReBAC engine
  was removed in the 2026-07 RBAC simplification and no longer exists.
- `mcp/` — FastMCP `server.py` (exposes `list_agency` tool / `agencies://list` resource,
  API-key authed) and `client.py`.
- `scheduler.py` — APScheduler jobs (see below).
- `concurrency.py`, `database.py`, `errors.py` (unified error envelope), `utils/` (uuid7, retry).

**Scheduler jobs (`app/scheduler.py`):**
- `agency_chat_test` every `HEALTH_CHECK_INTERVAL_MINUTES` (15): reachability-probes each
  non-draft/non-disabled agency via `test_connection` (same call as the admin endpoint —
  see **Connection test** below), logs to `ConnectionLog`, then `reconcile_statuses()`.
  Concurrency capped by `AGENCY_CHAT_CONCURRENCY`.
- `regenerate_brief_job` every `BRIEF_REGEN_INTERVAL_HOURS` (24) — weekly executive brief.

**Connection test (`app/services/agency.py: test_connection`)**

One reachability probe for every `connection_type`: HEAD with a GET fallback, bounded by
`CONNECTION_TEST_TIMEOUT`. **Any** HTTP response — including 4xx/5xx — means the endpoint is
reachable and counts as success; only a transport failure (refused / DNS / timeout) is an error.
No protocol-level handshake is performed: there is no POST chat probe, no MCP JSON-RPC
`initialize`, and no A2A chat query. Returns `success`, `protocol` (`REST API`|`MCP`|`A2A`|
`UNKNOWN`), `version` (always `-`), `steps[]`, `latency`, and the REST fields
`statusCode`/`statusText`/`server`/`contentType`. The `capabilities`/`server_info`/`agent_card`
response fields remain in the schema but are always null.

Both entry points share it: `GET /api/v1/agencies/{id}/test` (admin-only; also resets
`stats_reset_at`, clears rule-set `maintenance`, writes a `ConnectionLog`) and the scheduler's
`agency_chat_test`.
- `purge_old_connection_logs` every 24h (`CONNECTION_LOG_RETENTION_DAYS`, 90).
- `run_evaluation` every `EVAL_INTERVAL_HOURS` (168 / weekly) — golden-question LLM-judge eval.
- `regenerate_popular_questions` every `POPULAR_QUESTIONS_REGEN_INTERVAL_HOURS` (24): LLM-synthesizes
  clean คำถามยอดนิยม (purpose `popular_questions`) from successful user turns in the last
  `POPULAR_QUESTIONS_WINDOW_DAYS` (30). No-ops below `POPULAR_QUESTIONS_MIN_TURNS` (20) so the
  dopa/dol/fda seed shows on a fresh deploy. Churn: replaces only unpinned/unhidden `auto` rows;
  seed/manual/pinned/hidden untouched; hidden `text_key`s act as tombstones (never regenerated).
  Reads assistant `agency_ids` through `utils.clean_agency_ids` (splits comma-joined legacy
  elements like `["id1,id2"]` into lone UUIDs) so the `Agency.id__in` query never receives a
  malformed UUID — a raw joined value previously crashed the whole `regenerate` task on asyncpg.

**`utils.clean_agency_ids`** normalizes a message's `agency_ids` at every Python read site
(popular_questions regen, `messages` rating rollup, `feedback` low-rated + admin breakdown,
`insight` hourly-by-agency). Guards against legacy comma-joined elements: on Postgres a raw
`"id1,id2"` is an invalid UUID that crashes `Agency.get`/`id__in`; elsewhere it silently
mis-matches. (The DB-side `agency_ids__contains` filter in `feedback.py` can't use it and still
mis-counts such rows — accepted, no crash.)

**External integrations (config.py):** OpenRouter (`CLASSIFICATION_MODEL`
`google/gemini-2.5-flash-lite`), ThaiLLM parse-spec endpoint, OneChat (`ONECHAT_BASE_URL`, via
`services/onechat/`), MCP endpoint.
LLM providers/models are now also DB-configurable via `LlmProvider`/`LlmRoute` (admin pages):
a `LlmRoute` maps a `purpose` to a provider + model. **Purposes are centralized as a single
source of truth**: the `Purpose(StrEnum)` in `app/services/llm/purpose.py` (values
`classification`, `brief`, `judge`, `parse_spec`, `popular_questions`); `KNOWN_PURPOSES` derives
from it and is served by `GET /api/v1/llm/purposes`. All service call sites and `seed.py` use
`Purpose.*`; `schemas/llm_route.py` types `purpose` as `Purpose` so the create/update API 422s on
unknown values (no DB constraint). `GET /api/v1/llm/purposes` serves the list, but the **frontend
Routes panel is edit-only and shows `purpose` read-only** — a `listPurposes()` helper exists in
`llmRouteApi.ts` yet is currently unused (the UI offers no route create/delete). Route resolution
is cached (~30s) and invalidated on any provider/route mutation.

Each route can be **tested end-to-end** from the Routes panel: a per-card **ทดสอบ** button plus a
**ทดสอบทั้งหมด** header button (fires all purposes in parallel) hit
`POST /api/v1/llm/routes/{purpose}/test` (admin-only, 404 on unknown purpose). The endpoint calls
`services/llm.ping(purpose)`, which reuses the production `chat()` path with a 1-token prompt
(`max_tokens=1`, so cost is negligible and a usage row is recorded) and returns
`{ok, latency_ms, model, error}` — failures ride in `ok:false` (single 200 happy path). It resolves
the **enabled** route/provider only, so testing a disabled route returns `ok:false` "no enabled
route". The panel shows ✓ latency / ✗ error inline.

**Tests:** pytest (`asyncio_mode=auto`, `backend/tests/`), httpx AsyncClient transport.

## Data model (Tortoise ORM, `app/models/`)

| Model | Table | Purpose / key fields |
|---|---|---|
| `Agency` | `agencies` | Government agency. `connection_type` (API/MCP/A2A), `status` (draft/active/maintenance/disabled), `auto_maintenance`, `endpoint_url`, `expected_payload` (placeholder JSON), `api_headers`, `data_scope`, routing (`priority`, `router_hint`, `dispatch_timeout_s`, `mcp_tool_name`), `conformance_report`, metrics (`total_calls`, `rating_up/down`), `stats_reset_at`. `logo` holds an emoji **or** an uploaded-image URL (`/api/v1/agencies/{id}/logo?v=<hash>`). |
| `User` | `users` | Account. `role` = `user|staff|admin`, bcrypt `hashed_password`. |
| `UserAPIKey` | `user_api_keys` | Programmatic keys. `key_hash` (only hash stored), `key_prefix`, `expires_at`, `revoked_at`, `last_used_at`. Keys are prefixed **`tcg_`**. |
| `Conversation` | `conversations` | Chat session. `title`/`preview`, `agencies` (names), `status`, `message_count`, `external_session_id`, FK `user` (SET_NULL). |
| `Message` | `messages` | Turn message. `role`, `content`, `agent_steps`, `sources`, `summary` + `summary_references` (v5 executive summary and its citations; **not** named `references` — reserved SQL keyword), `rating`, `feedback_text`, `category` (Thai), `agency_ids`, `errors`, `parent_id`. |
| `ConnectionLog` | `connection_logs` | Every agency call/probe. `action` (test/query), `connection_type`, `status`, `latency_ms`, sanitized `request_body`/`response_body`, `message_id`/`assistant_message_id` (links to Message; enables cache). |
| `GoldenQuestion` / `EvalResult` | `golden_questions` / `eval_results` | Per-agency QA regression set + LLM-judge scores. |
| `ExecutiveBrief` | `executive_briefs` | Generated weekly narrative brief. |
| `LlmProvider` | `llm_providers` | LLM service (name, base_url, api_key, auth, rate limits, enabled). |
| `LlmRoute` | `llm_routes` | Maps a `purpose` (classification/synthesis/router/…) → provider + `model` (+ timeout). |
| `LlmUsage` | `llm_usage` | Token/cost tracking per call, dimensioned by user/agency/conversation/api_key. |
| `AuditLog` | `audit_logs` | Admin actions; denormalized `actor_email` survives user deletion. |
| `Setting` | `settings` | Runtime config overrides (key/value/type/group/is_secret), loaded at startup over env defaults. |
| `PopularQuestion` | `popular_questions` | คำถามยอดนิยม shown on portal/chat. `text`, unique normalized `text_key` (dedupe + hidden-tombstone), nullable `agency` FK (SET_NULL), `source` (seed/auto/manual), `pinned`, `hidden`, `sort_order`, `score`. Published = not-hidden, pinned→sort_order→score→recency, capped `POPULAR_QUESTIONS_DISPLAY_COUNT` (8). |

Migrations: **aerich** (`backend/migrations/`, **27 applied, `0`–`26`**; recent: `19` drop
embedding + add pg_trgm, `24` drop `relationships`/collapse roles, `25` drop rate-limit columns,
`26` promote `user`→`staff`). **Never hand-carry `MODELS_STATE`** —
always regenerate via `aerich migrate` against an upgraded DB. See `docs/aerich-migrations.md`
and the mandatory rules in `CLAUDE.md`.

## Auth & RBAC

- **Bearer token** = JWT (from `POST /api/v1/auth/login`) **or** a `tcg_` API key. Both resolve
  through `app/auth/dependencies.py::_resolve_token`. Optional-auth endpoints (chat, conversations)
  allow anonymous, but a **bad `tcg_` key is rejected (401)** rather than silently degrading.
  Any **`GET` under `/api/v1/public/`** (e.g. `public_status`, `popular_questions`) is exempt from
  the role chokepoint for **every** role — the shared frontend `apiClient` attaches the JWT on all
  requests, so an authenticated `user` hitting a public GET must not 403. Keep routers under
  that prefix strictly read-only. The chokepoint also exempts one non-`/public/` path: **`GET
  /api/v1/agencies/{id}/logo`** (public agency-logo image; `_AGENCY_LOGO_GET_PATTERN` in
  `auth/dependencies.py`, GET-only so the `POST` upload stays guarded). Uploaded logos are stored on
  the `agency-uploads` named volume (backend-only mount, `Settings.UPLOAD_DIR`) as content-hashed
  files and served by the backend with `immutable` caching — see ADR 0003.
- **Roles**: `user` (chat, architecture list, **own conversation history**), `staff` (everything
  `user` has **plus read-only** Dashboard · Executive · Agency Health · Usage Heatmap ·
  Usage Analytics · Feedback), and `admin` (full), plus anonymous. `user` ⊂ `staff` ⊂ `admin`;
  the only delta between `user` and `staff` is the six read-only dashboard GETs (`_STAFF_GET_EXACT`).
  New accounts default to least-privilege `user`; public self-registration for `user` is a planned
  follow-up (`docs/superpowers/specs/2026-07-23-rbac-staff-role-design.md`). The frontend login
  (`เข้าสู่ระบบ`) now serves both citizens and staff.
  On `/history` a non-admin sees and deletes **only their own** conversations: `list_conversations`
  filters `user_id` for non-admins, and the three detail handlers apply an own-or-admin check.
  `GET /history/{id}/messages` is allowlisted **GET-only** via
  `_HISTORY_MESSAGES_GET_PATTERN`, deliberately separate from the all-verbs
  `_HISTORY_PATH`, so a future write verb on that sub-resource does not inherit access.
  `staff` is read-only on those six pages: the staff allowlist grants only their six backing GETs
  (`_STAFF_GET_EXACT`), so writes like `POST /executive-summary/regenerate` stay admin-only
  and the UI hides the control (`canRegenerate={isAdmin}`) rather than letting it 403. A plain
  `user` cannot reach those six pages at all.
  **There is no public self-registration** — `POST /auth/register` and the `/signup` page were
  removed, because self-serve signup plus these grants would have let anyone reach the
  operational dashboards. Admins create accounts via `POST /api/v1/users`. Enforced by a
  **global chokepoint** `enforce_role_allowlist` (`dependencies.py`) that is **deny-by-default**:
  anonymous and unresolvable tokens pass through (so the endpoint's own auth returns 401 rather
  than a misleading 403), `admin` passes through to per-endpoint `require_admin`, and
  `_ROLE_ALLOWLIST` maps `user` → `_is_allowed_for_basic_user` and `staff` → `_is_allowed_for_staff`
  (= basic-user **+** `_STAFF_GET_EXACT`). **Every other role — including rows left behind by a
  not-yet-run migration — falls back to the least-privilege basic-user allowlist.** That fallback
  matters: an earlier design failed *open* for unknown roles, which would have let a residual
  `auditor` mint an API key during a deploy window.
  The `viewer`/`auditor`/`agency_owner` roles and the ReBAC/ABAC engine (`authz.py`,
  `relationships` table) were removed 2026-07 — see
  `docs/superpowers/specs/2026-07-23-rbac-simplification-design.md`.
- **The OpenAI programmatic surface is a shared write** (`_is_shared_write`), allowed for every
  authenticated role exactly like `/chat` — it is a programmatic surface, not a privileged one.
  Two subtree regexes grant it: `_RESPONSES_PATH` (`^/api/v1/responses(?:/.*)?$`) and
  `_OAI_CONVERSATION_PATH` (`^/api/v1/conversations(?:/.*)?$`). These are coarse role gates only;
  each endpoint under them enforces its own `owns()` ownership check (404, never 403), mirroring
  the `_HISTORY_PATH` precedent.
  The **WebSocket on that same path is not covered by the HTTP chokepoint** (a WS route is a
  different ASGI protocol): it resolves auth itself in `routers/responses.py::_ws_user`, from
  the `Authorization` header only. A bad or invalid token there degrades to anonymous
  rather than 401 — deliberate, and there is no query-param token fallback (it would leak keys
  into access logs).
- **MCP mount is intentionally outside** the role chokepoint (mounted sub-app bypasses FastAPI
  deps); MCP auth is by API key in `mcp/server.py` — any active user, no role check. See the big
  comment in `main.py` and `tests/test_mcp_role_access.py` before touching this.

## agent-proxy (`agent-proxy/`, Go)

Reverse proxy between backend and agency endpoints. `POST /agent-proxy/{agencyID}` looks up the
agency's `endpoint_url` + `api_headers` (`store.go` reads shared postgres via `DATABASE_URL` on
every request — no in-memory cache), forwards the request (strips inbound
`X-Forwarded*`, injects `api_headers`, 180s upstream timeout), streams the response back, **always**
writes a `connection_logs` row with `action="proxy"`, and increments `agencies.total_calls`
**only on a 2xx** upstream; a transport failure returns 502. Hand-rolled UUIDv7 ids, Asia/Bangkok
tz. Exports spans to Jaeger. `GET /health`.

## Tracing (cross-service, W3C)

A chat round-trip (user → portal → OneChat → /mcp → OneChat → agent-proxy → back) shares **one
trace id**, verified live in Jaeger. OneChat drops the `traceparent` header between hops but
preserves URL query strings, so the context is smuggled through the URLs we hand it (see URL
context below). `conversation_id` is also stamped on every service's spans as a correlation tag,
so fragments still join even if the header/URL path ever breaks. Frontend is out of scope (root
span = `POST /api/v1/chat/stream`).

- **Backend outbound** — `HTTPXClientInstrumentor().instrument()` in `app/main.py` injects
  `traceparent` on every outbound httpx call (OneChat, agency dispatch, LLM). `services/onechat/client.py`
  stays tracing-free by design.
- **OneChat call span** — `_stream_live` (`services/chat/stream.py`) wraps the event loop in an
  `onechat_call` span tagged with `conversation_id`.
- **MCP inbound** — the `/mcp` mount is wrapped in `OpenTelemetryMiddleware` (mounts are never
  covered by `FastAPIInstrumentor`) so an inbound `traceparent` continues the trace;
  `AuthMiddleware.on_request` tags the span with `conversation_id`. `excluded_urls` still lists `/mcp`
  to avoid double-instrumenting.
- **agent-proxy** — `initTracer` sets a composite `TraceContext`+`Baggage` propagator (default was
  no-op); `ServeHTTP` extracts inbound context before `Start` and injects the child span into the
  upstream request. `conversation_id` is resolved from the agency's `expected_payload` template
  (the key mapped to `__conversation_id__`), since the body field name varies per agency.
- **URL context smuggling** (`app/trace_util.py`) — the piece that unifies the trace across
  OneChat. `with_trace_query()` appends the active W3C context as a `?traceparent=` query param to
  the `mcp_endpoint_url` sent to OneChat (`stream.py`) and to the `/agent-proxy/{id}` callback URL
  (`_agent_proxy_endpoint`). On receipt, `QueryTraceparentASGI` (wrapping the `/mcp` mount) promotes
  the query param back to a header before OTel extracts, and agent-proxy's `ServeHTTP` extracts
  `traceparent` from the query when no header is present. A real header always wins.
- **Verify** — `docs/tracing-verification.md`: POST `/api/v1/chat/stream` with a known `traceparent`,
  then `GET /jaeger/api/traces/<id>` — spans from **both** `backend` and `agent-proxy` under the one
  id confirm unification (last run: 82 spans, both services).

## Frontend (`frontend/`, React SPA)

React 18 + Vite 5 + TypeScript, **shadcn/ui** (Radix + Tailwind), **TanStack Query**, **axios**,
**react-router-dom v6**, react-hook-form + zod. **Feature-based** layout under `src/features/*`
(one dir per page: chat, dashboard, executive, health, heatmap, agencies, history, architecture,
connection-logs, api-keys, settings (SettingsLayout — merges settings/llm/api-keys/usage/connection-logs/audit
into one tabbed `/settings` area), llm (merged LLM Settings page), llm-providers, llm-routes, popular-questions, users, audit,
usage, feedback, public, status, auth). Shared code in `src/shared/*`. Package manager = **pnpm** (Dockerfile uses
`pnpm --frozen-lockfile`; stray `bun.lock`/`package-lock.json` are not authoritative).

- **API layer** (`shared/lib/apiClient.ts`): axios, base URL `VITE_API_BASE_URL` (defaults to
  `window.location.origin` → same-origin via nginx). Request interceptor attaches JWT from
  `localStorage['auth_token']`; response interceptor unwraps the `{error:{message}}` envelope
  (with legacy `detail` fallback).
- **Auth**: `features/auth/useAuth` + `ProtectedRoute`. Public routes: `/`, `/about`,
  `/data-policy`, `/contact`, `/status`, `/login`. There is no password-reset or email-invite
  flow — admins create users with an initial password (`POST /users`) and can change any user's
  password via `PATCH /users/{id}` (optional `password` field); login is the only credential
  entry point. Any authenticated user changes their own password via
  `POST /auth/change-password` (requires the current password) — reached from the key-icon
  button in the sidebar user section (`ChangePasswordDialog`). All masked fields (passwords and
  secret API keys) use the shared `shared/components/ui/password-input` `PasswordInput`, which
  adds an eye-icon show/hide toggle. `LoginPage` has a "กลับสู่หน้าหลัก" (back to home) link to `/`
  below the form.
  Authenticated routes are role-gated in `App.tsx`, mirroring backend RBAC (e.g. `/chat` +
  `/architecture` any role; `/popular-questions` admin-only). **Seven admin pages are merged into a
  tabbed Settings area** `features/settings/SettingsLayout` at `/settings`: System settings, LLM,
  API Keys, User management, Usage, Connection logs, Audit log — one nested route per tab
  (`/settings/system`, `/settings/llm`, `/settings/api-keys`, `/settings/users`, `/settings/usage`,
  `/settings/connections`, `/settings/audit`). `SettingsLayout` renders a role-filtered `TabsList` (via the shared
  `canAccess`) + `<Outlet/>`; the active tab derives from the URL. `/settings` itself is
  authenticated-only (it holds the all-roles **Usage** tab), while each admin tab is individually
  wrapped in `<ProtectedRoute requireAdmin>` so a non-admin deep-linking to e.g. `/settings/audit`
  is blocked, not merely hidden; the index redirects by role (admin→system, else→usage). The old
  top-level paths (`/api-keys`, `/users`, `/usage`, `/connection-logs`, `/audit-log`,
  `/llm-settings`, `/llm-providers`, `/llm-routes`) `<Navigate replace>` into their new tab. `roles.ts`
  (`ROUTE_ROLES`, single source of truth) sets `/settings`=all-roles + per-child access, and the
  sidebar collapses the six former entries into a single **ตั้งค่าระบบ** link. **LLM admin is one
  merged page** `features/llm/LlmSettingsPage` (now the `/settings/llm` tab)
  (Providers left / Routes right, two-column on `md`+): `ProvidersPanel` (full CRUD) +
  `RoutesPanel` (edit-only — no create/delete; edits provider, model, timeout, enabled).
  The portal/chat คำถามยอดนิยม block is fed by the anonymous
  `GET /public/popular-questions` (no more hardcoded `suggestedQuestions` in `mockData.ts`).
  The public portal's หน่วยงานที่เชื่อมต่อ block (`AgencyCards` + `usePublicAgencies`) is fed by
  the anonymous `GET /public/agencies`. In **chat mode** the portal switches to a `SidebarProvider`
  layout (like the staff `AppLayout`) with `features/public/PublicSidebar` — a public, auth-free
  mirror of `AppSidebar` showing a single **แชทใหม่** action (calls `useChat().reset`, no
  navigation) plus the same หน่วยงานที่เชื่อมต่อ list. The portal header is stripped to just the
  **เข้าสู่ระบบ** login control, rendered as an outline pill `Button` linking (react-router `Link`)
  to `/login` — **not** `/chat`: once a visitor sends a chat message the app bootstraps an
  *ephemeral* anon session (`ensureSession` → `POST /auth/anon`), so `ProtectedRoute` (which only
  checks `!user`) would wave them straight into `/chat` still anonymous. `/login` is correct because
  `LoginPage` only redirects away *real* users (`user && !user.isEphemeral`), so an ephemeral user
  still sees the login form.
- **Agency detail** (`features/agencies/detail/`): tabs ภาพรวม · Health · **แก้ไข (Edit)** · Logs.
  The Edit tab (`EditTab`) — shown to admins, the only role that can reach the page — consolidates
  General/Connection/Routing editing, each a section with its own save. It replaced the former standalone Connection/Routing tabs. The setup wizard
  (`/agencies/{id}/setup`) still handles guided first-time setup + activation. Editing any
  connection-identity field on an **active/maintenance** agency demotes it to `draft` (see below +
  ADR `docs/adr/0002-agency-edit-connection-demote.md`); the Connection section confirms before
  saving such a change. The card's แก้ไข action deep-links to `/agencies/{id}?tab=edit` (detail
  page reads `?tab=`; read-only users fall back to overview). The General section's **color** field
  is a native `<input type="color">` (shared `ColorField`; legacy `hsl()` values are converted to
  hex via `features/agencies/color.ts`), and its **logo** accepts an emoji **or an uploaded image**
  (upload button → `useUploadAgencyLogo`; image-only in the Edit tab). Agency logos everywhere
  render through the shared `shared/components/AgencyLogo` (`<img>` for `/api/`·`/uploads/`·`http`·
  `data:` values, else the emoji). See ADR `docs/adr/0003-agency-logo-image-upload.md`.
- **Chat streaming** (`features/chat/chatApi.ts`): consumes `/chat/stream` SSE via native `fetch`
  (events `step` — including v5's `summarize`, `agencies`, `intent`, `routing`, `agency_start`,
  `agency_responded`, `agency_verified`, `answer`, `done`, `error`), with a per-chunk idle timeout
  and a JSON-polling fallback. The v5 `summary` + `references[]` render in the shared
  `shared/components/SummaryCard` above the raw sections;
  `shared/lib/summary.ts::stripSummaryPrefix` strips the duplicate summary prefix from
  the composed `answer` (upstream embeds summary → refs → `---` → sections in one string). The
  same pair renders stored summaries in the history detail dialog (`features/history/MessageItem`).
  Message rating uses optimistic UI updates. The message list + typing indicator and the input bar
  are shared components — `features/chat/ChatConversation` and `features/chat/ChatInput` — reused by
  both the staff `ChatPage` and the public `PublicPortal` (chat mode) so the two stay in sync.
  The staff sidebar's **แชทใหม่** item (`AppSidebar`) navigates to `/chat`; when already on `/chat`
  it instead pushes `/chat?new=1`, and `ChatPage` resets the conversation on that `new` flag (then
  clears it). The public portal's แชทใหม่ resets directly via `useChat().reset`.
- **Serve**: multi-stage Dockerfile → `vite build` → static `dist/` served by nginx
  (`frontend/nginx.conf`, SPA fallback). Container healthcheck hits **`/healthz`** (not `/health`,
  which is a client route).
- `frontend/supabase/` is **vestigial** (legacy edge functions/migrations; not referenced by `src`;
  the app talks only to the FastAPI backend).
- **Tests**: vitest + jsdom + **MSW** (`src/mocks`, `src/test`). `VITE_USE_MOCKS=true` enables MSW in
  the browser for mock-backed local runs.

## Infrastructure, CI/CD, deployment

- **Branches**: `main` = prod (protected, **PR-only**, deploys to prod), `dev` = dev env.
  Branch off `dev` → PR into `dev`; promote via PR `dev` → `main`. Never push `main` directly.
- **`.github/workflows/test.yml`** (on PR / manual): parallel jobs — backend `pytest` (with redis
  service), agent-proxy `go build && go test`, frontend `tsc --noEmit` + vitest coverage, and
  `scripts` (`./scripts/tunnel-url_test.sh`). **No E2E** (removed from CI).
- **`.github/workflows/deploy.yml`** (merged PR to `main` / manual): self-hosted runner, validates
  `JWT_SECRET`/`OPENROUTER_API_KEY`, writes prod `.env` (`ENV=production`), then
  `docker compose up -d --build --remove-orphans`. Deploy does **not** depend on the test job.
- **Prod env** template: `.env.prod.example` (set `JWT_SECRET`, `POSTGRES_PASSWORD`, `CORS_ORIGINS`,
  OneChat URLs, `OPENROUTER_API_KEY`). `ENV=production` makes startup refuse the default JWT secret.

## Testing suites

- **backend/tests** — pytest (`asyncio_mode=auto`), in-process httpx AsyncClient over a SQLite
  `:memory:` DB; Postgres-only paths (pg_trgm similarity, some analytics SQL) are `skipif`-gated on
  `TEST_PG_URL`. The RBAC "access matrix" now lives here as `test_basic_user_allowlist` /
  `test_staff_allowlist` / `test_residual_role_denied` / `test_mcp_role_access` / `test_surface_parity`.
- **frontend** — vitest + jsdom + MSW, colocated `*.test.tsx`/`*.test.ts` throughout `src/features`.
- The former standalone **`blackbox/`** (vitest access-matrix) and **`e2e/`** (Playwright) suites
  were **removed from the tree** — neither directory exists anymore, and E2E is not in CI.

## Agency integration contract (for `examples/reference-agency`)

An `API` agency exposes an HTTP `POST` endpoint. The gateway builds the body from
`expected_payload` with placeholder substitution (`__query__`, `__session_id__`,
`__conversation_id__`, `__user_id__`) and sends `api_headers` (lowercased) + `content-type: json`.
**Return HTTP 200 for every valid question** (non-2xx = error contribution). Before `draft → active`,
an agency must pass a **5-check conformance battery**: `responds`, `non_empty`, `thai_text`,
`concurrency_3`, `garbage_input` (stored in `agency.conformance_report`). The **setup wizard** is
the only UI that runs it: `StepTest` calls `POST /agencies/{id}/conformance` (`useRunConformance`)
and the review-step **เปิดใช้งาน** button stays disabled until the report passes. The detail-page
status dropdown therefore omits the direct `draft → active` option (other transitions, incl.
`maintenance/disabled → active`, are unaffected — the gate only blocks `draft → active`). Editing any
connection-identity field (`connection_type`/`endpoint_url`/`api_headers`/`expected_payload`/
`mcp_tool_name`) of an **active** or **maintenance** agency demotes it back to `draft` and clears
`conformance_report` — done atomically in `PATCH /agencies/{id}` (a system reset that bypasses the
`is_legal_transition` guard, which otherwise forbids `→ draft`); `disabled`/`draft` are unaffected
and general/routing edits never demote. See ADR `docs/adr/0002-agency-edit-connection-demote.md`.
Transient errors retry up
to 3× with backoff; 4xx/5xx do not. `MCP` and `A2A` connection types are also supported.
Full spec: `docs/agency-integration.md`; API-consumer guide: `docs/quickstart.md`.

## Documentation & specs map

- `docs/quickstart.md` — API consumer flow (get `tcg_` key, auth, `/chat`, `/chat/stream`, errors).
- `docs/agency-integration.md` — agency endpoint contract, health probes, conformance.
- `docs/aerich-migrations.md` — migration discipline (never fake `MODELS_STATE`).
- `spec/roadmap.md` — product vision & phased roadmap (security → cost tracking → reliability →
  chat consolidation → agency self-service/authz → trust/quality).
- `spec/openai-responses.md` — the OpenAI Responses API wire contract we implement (models,
  `input` forms, continuity, the streamed event sequence, the `portal` block, error codes,
  WebSocket frames, and the documented deviations from OpenAI).
- `spec/v4-streaming.md`, `spec/mcp-server.md`, `spec/agent-*.md` — OneChat v4 SSE event spec, MCP
  server contract, and orchestrator/agency integration notes.
  ⚠️ `spec/agent-20260623.md`, `agent-onechat.md`, `agent-promes.md` contain **real agency/Dify API
  keys flagged for rotation** — treat as secrets, do not propagate.

## Conventions & gotchas

- **Popular-questions agency mapping is grounded in real turn data, not LLM name-guessing.**
  `services/popular_questions.regenerate()` no longer asks the LLM to guess an agency *name* and
  match it via `name__iexact` (unreliable). Each turn already stores the real `agency_ids` on the
  **assistant** message, linked to the question by `parent_id`. `_build_samples()` joins each
  recent successful user question to its reply's agencies (`{text, agencies:[{id,name}]}`); the
  LLM prompt feeds `question [หน่วยงาน: …]` pairs plus a `name = id` reference block and asks for
  an `agency_id` back. The returned id is resolved **only** against the set of agencies actually
  fed (`agency_by_id` from `valid_ids`) — hallucinated, unknown, empty, *or real-but-unfed* ids all
  resolve to `None`. Churn/dedupe/tombstone/public-shape logic unchanged.
- After any completed code change: **update this `context.md`, then commit**; on merge to `main`,
  **rebuild docker compose**.
- **Multi-task work → create a branch first** (`feat/`, `fix/`, `chore/`, `refactor/`); never commit
  multi-step work to `main`. Do **not** use claude worktree.
- **All OneChat calls go through `services/onechat/`** — never POST an upstream URL inline. The
  client is transport-only (`chat_v1/v2/v3`, `stream_v4/v5`, the version-uniform `events()`,
  `resolve_version()`, `health`; `get_client(version)`); it maps errors uniformly (non-200→status, `ReadTimeout`→504, other→502) as
  `OneChatError`, and callers keep persistence/tracing. Paths derive from `ONECHAT_BASE_URL`; inject
  `httpx.MockTransport` via `OneChatClient(transport=...)` to test without a live upstream.
- **TDD is mandatory** (red → green → refactor). Go changes: run `/use-modern-go`, then gofmt +
  `golangci-lint run --allow-parallel-runners` (repeat until clean).
- Prefix all shell commands with **`rtk`** (token-optimizing proxy) — see `docs/rtk.md`.
- Agencies router registers literal paths (`/mcp/discover`, `/parse-spec`) **before**
  parametric `/{agency_id}` to avoid UUID wildcard shadowing (`routers/agencies/__init__.py`).
  Note the flip side, now that `/mine` is gone: an unmatched literal falls through to
  `/{agency_id}` and returns **422** (UUID validation), not 404.
- Error responses use a unified envelope `{"error":{"code","message","retryable","upstream_status"}}`
  (`app/errors.py`); frontend unwraps it, with legacy `detail` fallback.
- **Responses surface has no rate/quota enforcement.** `/api/v1/responses` only ever produces
  `invalid_request_error` and `server_error` types — there is no `_enforce_limits`,
  `rate_limit_exceeded`, or `quota_exceeded` in the responses router/services (unlike `app/errors.py`,
  which has its own `quota_exceeded` for other routes). WS defaults live in `app/config.py`:
  `RESPONSES_WS_MAX_CONNECTIONS = 1024`, `RESPONSES_WS_MAX_DURATION_SECONDS = 900` (15 min), and the
  limit frame interpolates the value in **seconds**. `spec/openai-responses.md` was corrected to match
  (it had drifted to fabricated rate/quota rows and stale 100/3600/"60 minutes" values).
- **`spec/openai-responses.md` was a complete *output* contract but not a complete *build* contract —
  now fixed.** A spec-first rebuild of the responses layer produced **25/25 byte-identical** wire
  output (pinned-upstream differential diff), but only after resolving 8 wire-visible gaps from the
  code. Those gaps are now closed in the spec: a new **"Upstream input — the OneChat `ChatEvent`
  stream"** section (between §3 and §4) documents the `answer`/`done`/`error` inputs to
  `translate.consume()` and the `answer` payload shape feeding `portal.agency_ids`
  (`sections[].agencies[].id`); §5 states the `ensure_ascii=False` UTF-8 rule; §4 states that response
  `model` echoes the request verbatim and `output` stays `[]` on an empty answer; and the previously
  unstated error `message` strings (input validation §2.1, conversation mismatch §3, binary frame §8)
  are now pinned. Full findings + fix list: `spec/openai-responses-spec-gap-log.md`.
  A follow-up code↔spec reconciliation (2026-07-24) found **zero wire divergences** — the layer
  passes all 49 responses tests and conforms to the contract; the only change was deleting the
  dead `ResponseAccumulator.failed_event()` (unreferenced; `_failed` is used directly).
- **Editing `frontend/vite.config.ts` does not affect a running stack.** The dev override's
  `develop.watch` syncs only `frontend/src`, and `docker compose up` will not rebuild an existing
  image — so config changes silently do nothing until `docker compose up -d --build frontend`.
  This is what made the tunnel serve `Blocked request` despite `allowedHosts` being correct in
  source; a unit test would not have caught it.
- **Frontend tests cannot use the `node` environment, and cannot import `vite.config.ts`.**
  `vitest.config.ts` applies `setupFiles: ["./src/test/setup.ts"]` to every file in that file's own
  resolved environment, and `setup.ts` unconditionally touches `window` — so
  `// @vitest-environment node` throws `ReferenceError: window is not defined`. Staying in jsdom
  instead breaks differently: jsdom's realm does not share `Uint8Array` with Node's, so importing
  `vite` crashes esbuild's cross-realm invariant, and jsdom's `URL` ignores a `file://` base, so
  `new URL(..., import.meta.url)` + `readFileSync` fails too. Root cause is `jsdom@20` under Node
  24. A regression test for `allowedHosts` was dropped for this reason (covered by the tunnel smoke
  check instead); fixing `setup.ts` to tolerate a missing `window` is deferred to its own `chore/`
  branch.
- **Chat text-scale control (A / A / A).** `TextScaleProvider` + `useTextScale`
  (`frontend/src/shared/hooks/useTextScale.tsx`) hold a persisted `small|normal|large` preference
  (localStorage key `chat-text-scale`), wrapped once around the router in `App.tsx`. The
  `TextScaleControl` buttons render only in the chat context — the `PublicPortal` chat-mode header
  and the shared `AppLayout` header on `/chat`; the `PublicPortal` landing header no longer shows
  them (scaling targets chat content, and there is nothing to scale on the landing page).
  `ChatConversation` scales via a **container `font-size`** (`fontSize: ${factor}em`), *not* CSS
  `zoom`, so only text reflows (padding/avatars/spacing stay fixed). For this to cascade, the
  readable body text in `MessageBubble` was switched from fixed rem classes to `em`-relative ones —
  the bubble uses `text-[1em]` and the markdown body `prose-sm text-[0.875em]`; chrome text
  (timestamps, sources, thinking) stays fixed. Factors: 0.875 / 1 / 1.25.
- **Shared assistant reply rendering (`AssistantMessageContent`).** The thinking panel + markdown
  answer + summary card were duplicated across live chat (`MessageBubble`) and history
  (`MessageItem`), which had drifted (history rendered without `remark-gfm`, thinking collapsed,
  summary nested in the bubble). Extracted `frontend/src/shared/components/AssistantMessageContent.tsx`
  — takes normalized `{ content, summary?, references? }`, owns `parseThinkContent` +
  `stripSummaryPrefix`, and renders the three as separate stacked cards in order **thinking →
  answer bubble → summary**, with the thinking panel open by default. Both call sites now consume it
  (each keeps its own chrome: `MessageBubble` = user bubble + sources + rating + timestamp;
  `MessageItem` = Bot/User avatars inside the history dialog), so `/history` and `/chat` stay
  visually identical and can't drift again. Covered by `AssistantMessageContent.test.tsx`. The
  `SummaryCard` (`shared/components/`) is collapsible, **collapsed by default** (a `สรุป` toggle with
  a chevron, matching the Thinking/Agent-steps panels) — the executive summary and its `[n]`
  references are hidden until expanded. Consumer tests click the toggle before asserting summary
  content. The
  answer-bubble styling is exported as `ASSISTANT_BUBBLE_CLASS` from the same module and reused by
  the `ChatConversation` typing placeholder (lines 31–47) so the "assistant is working" bubble and
  the real answer bubble share one source of truth. Covered by a class-match assertion in
  `ChatConversation.test.tsx`.
- **Persisted agent-step pipeline snapshot.** The AI-agent pipeline progress (steps + timings,
  per-agency statuses, errors) used to be live-only via `StreamingProgress` and was dropped before
  the assistant message was saved — the `Message.agent_steps` JSON column existed but was never
  populated. Now `/chat/stream` captures the streamed `step`/`agency_start`/`agency_responded`/
  `agency_verified` events and folds them into a snapshot via the pure
  `build_pipeline_snapshot(events, errors)` (`backend/app/services/chat/pipeline_snapshot.py`),
  which `_stream_live` → `_persist` → `save_turn(agent_steps=...)` writes to `agent_steps` (snake_case
  object, or `[]` when empty; cached replays store `[]`). No migration — the column was reused.
  History already returns the field. Frontend: `AgentStepsSnapshot` (camelCase) in
  `shared/types/chat.ts`; a new `ChatMessage.pipeline` carries the live snapshot (built in
  `buildAiMessageFromState`), while history normalizes the persisted shape via
  `toAgentStepsSnapshot` (`shared/lib/agentSteps.ts`). The shared `AgentStepsCard`
  (`shared/components/`, collapsible, collapsed by default) renders it **after** the summary in
  `AssistantMessageContent`, so both `MessageBubble` and `MessageItem` show it. The legacy
  `ChatMessage.agentSteps: AgentStep[]` field is untouched. `/chat/stream` only — the OpenAI
  Responses API still drops pipeline events. The `AgentStepsCard` expanded body is styled after the
  OneChat debug console's `FlowPanel` (`185-84-160-55/xver/one-chat/.../FlowPanel.tsx`, a reference
  copy in-repo): a summary-chip row (ผ่าน/ไม่ผ่าน/error counts), a vertical step timeline with
  lucide icon nodes + Thai `STEP_META` descriptions + `เสร็จ · Ns` badges, and a separate
  `หน่วยงาน` block of per-agency verdicts below it (model/detail lines from FlowPanel are omitted —
  not persisted). In `AssistantMessageContent` the card renders **before the answer** (order:
  Thinking → Agent steps → Answer → Summary). The live typing indicator in `ChatConversation` reuses
  the same `AgentStepsCard` (`defaultOpen` + `loading`, fed by
  `buildAgentStepsSnapshot(streamingState)`) instead of the old
  `StreamingProgress`/`AgentStepDisplay` — so live and persisted pipeline views are one component.
  The `loading` prop appends an amber spinner node (`กำลังทำงาน…`) after the last completed step
  while streaming (persisted cards omit it); the bouncing dots remain for the initial moment before
  the first step completes. The card's text uses **`em`-relative sizes** (`text-[0.75em]` etc.) so it
  scales with the chat text-scale control alongside the message body; in history (no scaling
  container) it renders at its default size. Spec:
  `docs/superpowers/specs/2026-07-26-persist-agent-steps-design.md`; plan:
  `docs/superpowers/plans/2026-07-26-persist-agent-steps.md`.
- **MCP `endpoint_url` scheme behind Cloudflare.** `_fetch_agencies` rewrites every `API` agency's
  `endpoint_url` to `<scheme>://<X-Forwarded-Host>/agent-proxy/<id>`. It used `request.url.scheme`,
  which is `http` in this deployment: the whole chain (cloudflared → nginx → backend) speaks plain
  HTTP, and nginx overwrites `X-Forwarded-Proto` with its own `$scheme` (= http). The only header
  carrying the browser's real scheme is Cloudflare's `cf-visitor` (`{"scheme":"https"}`), so clients
  were handed an `http://` proxy URL that a https origin rejects. `_external_scheme(request)`
  (`app/mcp/server.py`) now resolves scheme as **cf-visitor → X-Forwarded-Proto → connection
  scheme**. Covered by `tests/test_mcp_endpoint_scheme.py`. Also dropped the debug `print`s that were
  dumping full request headers (incl. `Authorization`) to stdout on every call.
- **Ephemeral users hidden from admin user list.** Anonymous public-portal visitors are persisted
  as `User.is_ephemeral = True` accounts. `list_users` (`app/routers/users.py`, `GET /users`) now
  bases its queryset on `User.filter(is_ephemeral=False)` so temp-users never appear in the admin
  user-management screen and don't inflate `total`. Backend-level filter only — no frontend change,
  no opt-in flag; the other by-ID endpoints are unchanged. Covered by
  `test_list_excludes_ephemeral_users` in `tests/test_users_router.py`. Spec:
  `docs/superpowers/specs/2026-07-26-hide-ephemeral-users-design.md`.
- **Unified chat endpoint (one path, three transports, all OneChat versions).** The three chat
  routes were merged into a single path `/chat`. `POST /api/v1/chat` (`app/routers/chat.py`) serves
  JSON by default and SSE when the request body has `stream: true`; `WS /api/v1/chat` is a second
  handler on the same path (ASGI dispatches HTTP vs WebSocket by scope type). The old
  `POST /chat/external` and `POST /chat/stream` are **deleted** (hard cutover). All three transports
  drive the one existing transport-free pipeline `prepare_turn` + `run_turn`
  (`app/services/chat/stream.py`), so the sync path now shares caching/persistence/classification
  with the stream path — including that a cache replay writes a `ConnectionLog` (a cached copy can
  re-seed the similarity cache; consistent with the old SSE path, accepted by design). The old
  sync-only `_copy_cached_answer` and the v3-direct `chat_v3` router path are gone. OneChat version
  (v1–v5) is selected OpenAI-style via a `model` field: `resolve_model_version(model)`
  (`app/services/chat/model.py`) maps `onechat`/omitted/unknown → v5 and `onechat-vN` → `vN`
  (lenient), threaded to `prepare_turn(requested_version=...)`. The sync JSON response is a
  version-faithful passthrough: `{ success, data: { message_id, cached, agentSteps, ...<the
  version's answer-event payload> }, conversation_id, responseTime }`, built by `collect_turn`
  (`app/services/chat/aggregate.py`) draining `run_turn`. WebSocket logic lives in
  `app/services/chat/ws.py` (`ConnectionRegistry`, header-bearer `bearer_user`, `handle_chat_frame`)
  mirroring `responses.py`; new settings `CHAT_WS_MAX_CONNECTIONS` / `CHAT_WS_MAX_DURATION_SECONDS`.
  Frontend migrated: `chatApi.ts` posts SSE to `/api/v1/chat` with `stream: true` (was
  `/chat/stream`), `ChatApiResponse` is the passthrough envelope with a `ChatReference` type;
  `useChat.ts` and `agencyApi.ts` read the new optional fields with fallbacks (old `data.agencies`/
  `data.confidence` removed). Spec:
  `docs/superpowers/specs/2026-07-27-unified-chat-endpoint-design.md`; plan:
  `docs/superpowers/plans/2026-07-27-unified-chat-endpoint.md`.
- **Cookie session auth (Phase A) — JWT removed.** Browser auth is now an opaque
  server-side session, not a JWT. `POST /auth/login` verifies the password, creates a
  Redis session (`app/services/auth_session.py`: `session:<id> → user_id`, TTL
  `SESSION_TTL_MINUTES`, in-process fallback when `REDIS_URL` is empty) and sets an
  `HttpOnly; Secure; SameSite=Lax` cookie (`settings.SESSION_COOKIE_NAME`); it returns
  `{user}` with **no token**. `POST /auth/logout` deletes the session + clears the cookie
  (revocation is inherent — no blocklist). Auth resolution (`app/auth/dependencies.py`)
  is unified across both chokepoints (`get_current_user*` and the global
  `enforce_role_allowlist`/`_resolve_role`) with ONE precedence rule: **an
  `Authorization: Bearer` header decides (API-key only; 401 on failure, no cookie
  fallback); the session cookie is used only when no header is present.** This closes an
  allowlist-bypass (bogus bearer + valid cookie). Optional-auth asymmetry kept: bad API
  key → 401, missing/expired session → anonymous. **JWT is gone** (`create_access_token`/
  `decode_access_token`, `JWT_*` settings, `assert_production_secrets` removed);
  machine clients use API-keys (`tcg_`). A `SessionRefreshMiddleware`
  (`app/middleware/session_refresh.py`) re-rotates a session when its remaining TTL drops
  below `SESSION_REFRESH_BELOW_MINUTES` (sliding window; new id + fresh cookie, old id
  deleted). `/responses` + `/conversations` now **require** auth (`get_current_user`); the
  auto-ephemeral-user flow (`owner_or_ephemeral` + `X-Portal-Session`) is removed. CORS
  gained `allow_credentials=True` with explicit (non-wildcard) origins; a new
  `assert_production_config` rejects wildcard CORS in production. Frontend is **header-
  free**: axios `withCredentials`, no `Authorization`, `tokenStorage` deleted; session is
  restored on mount via `GET /auth/me` and ended via `POST /auth/logout`; the two raw
  `fetch` sites (SSE, logo upload) send `credentials: 'include'`. **Phase C** (anonymous
  `/chat` session) and **Phase D** (WS reads the cookie + WS-default chat) follow. Spec:
  `docs/superpowers/specs/2026-07-27-cookie-session-auth-phaseA-design.md`; plan:
  `docs/superpowers/plans/2026-07-27-cookie-session-auth-phaseA.md`.
- **Anonymous sessions + WS-default chat (Phase C+D).** Anonymous public-portal visitors
  get a persistent session: `POST /auth/anon` (`app/routers/auth.py`, idempotent) mints an
  `is_ephemeral` user + session cookie on first chat (created only when they chat, not per
  page-load). The frontend calls it via `useAuth().ensureSession()` before the first turn
  (no-op if already authenticated/anon). Anon works for `/chat` + own history but the
  OpenAI-compat surfaces reject it: `get_current_user_non_ephemeral` (401 on `is_ephemeral`)
  gates every `/responses` + `/conversations` HTTP endpoint, and the `/responses` WS closes
  anon/None callers. `verify_password` now returns `False` on an unusable hash (anon's `"!"`)
  instead of raising; `change-password` + `PATCH /me` require non-ephemeral. **WS cookie
  auth:** both `/chat` and `/responses` WebSockets resolve the caller via `app/auth/ws.py`
  `resolve_ws_user` (header API-key decides, else session cookie — same precedence as HTTP)
  behind `ws_origin_allowed` (CSWSH defense: the handshake `Origin` must be in
  `CORS_ORIGINS`, checked before accept; close 1008 otherwise). `/chat` WS allows anon
  sessions; `/responses` WS requires non-anon. **Frontend WS-default:**
  `useChatStream.startStream` tries `sendChatQueryWS` (`chatApi.ts`) first, falling back to
  SSE then JSON. Fallback is safe against double-running a turn — WS falls back to SSE ONLY
  if the socket closed before its first frame; a mid-stream death resolves `true` and
  `finalizeStreaming` renders the partial answer / a connection-lost bubble. `AuthUser`
  gained `isEphemeral`; `LoginPage` no longer redirects an anon user away from `/login`.
  Anon-user pruning is a documented follow-up. Spec:
  `docs/superpowers/specs/2026-07-27-chat-ws-default-phaseCD-design.md`; plan:
  `docs/superpowers/plans/2026-07-27-chat-ws-default-phaseCD.md`.
- **WebSocket handshake fix + open CORS.** Every `/chat` and `/responses` WebSocket returned
  HTTP 500: the global `enforce_role_allowlist` dependency (`app/auth/dependencies.py`,
  wired in `app/main.py`) required a `Request`, which FastAPI cannot inject for a WS
  handshake → `TypeError` before the handler ran. Fixed by typing it `HTTPConnection` and
  skipping non-`http` scopes (WS routes self-authenticate via `resolve_ws_user` +
  `ws_origin_allowed`); the HTTP allowlist is unchanged (`scope["method"]`/`scope["path"]`).
  Regression test wires the global dep onto a WS route like `app.main`. Also: `ws_origin_allowed`
  now accepts same-origin handshakes (`Origin` host:port == `Host`), so a same-origin WS
  through nginx works without listing the exact origin. Per request, CORS is now wide-open:
  `CORS_ORIGINS` defaults to `["*"]` (Starlette reflects any origin with credentials) and the
  `assert_production_config` wildcard guard was removed — `"*"` also short-circuits the WS
  Origin gate. Residual cross-site risk is mitigated by `SameSite=Lax` session cookies and
  header-based API keys.
- **Hide test-action connection logs by default.** `/settings/connections`
  (`ConnectionLogsPage`) was showing every `ConnectionLog`, including automated
  `action="test"` health-check rows. New `include_test` bool query param (default `false`)
  on `GET /connection-logs` and `/connection-logs/info` (`app/routers/connection_logs.py`):
  when off, `qs = ConnectionLog.all().exclude(action="test")` is applied at the queryset
  root — before search/agency/status/type filters, pagination, and the
  total/successful/failed/avg-latency aggregates — so the stat tiles always match the
  visible table. Frontend adds a `แสดงการทดสอบ` pill toggle (`ConnectionLogFilters.tsx`)
  that sends `include_test=true` only when on (omitted otherwise); `includeTest` is threaded
  through `useConnectionLogs`/`useConnectionLogInfo` (in both query keys), folded into
  `hasFilters`, and cleared by `resetFilters`. Spec:
  `docs/superpowers/specs/2026-07-28-hide-test-connection-logs-design.md`; plan:
  `docs/superpowers/plans/2026-07-28-hide-test-connection-logs.md`.
- **Deploy build-cache: persist layer cache + incremental Vite.** Deploy runs
  (`docker compose up -d --build`, ~112-145s) occasionally spiked because BuildKit
  `--mount=type=cache` dirs (uv/go-mod/pnpm/go-build) are builder-local and get wiped by
  `docker system prune`/GC/daemon restart → cold dependency reinstall. Fix 1: new deploy-only
  overlay `docker-compose.cache.yaml` (layered by the Deploy workflow only, never local
  `docker compose up`, whose default driver can't export local cache) adds
  `cache_from`/`cache_to type=local,dest=${BUILDCACHE_DIR:-/opt/deploy-buildcache}/<svc>,mode=max`
  per built service. `deploy.yml` now creates an idempotent container-driver buildx builder
  (`docker buildx create --name deploy --driver docker-container`), sets `BUILDCACHE_DIR`,
  `COMPOSE_BAKE=true`, `BUILDX_BUILDER=deploy`, and passes `-f docker-compose.cache.yaml`.
  Unchanged lockfiles → dep-install *layer* restored from the host dir even on a cold builder,
  so no reinstall. Fix 2: `frontend/Dockerfile` builder adds
  `--mount=type=cache,target=/app/node_modules/.vite` to `pnpm run build` (minor — Vite
  production/Rollup builds don't cache incrementally without a plugin; the real frontend win is
  Fix 1 skipping `pnpm install`). One-time runner prereq is auto-handled by the workflow step;
  cache lives under `$HOME/deploy-buildcache`. Not yet validated on the self-hosted runner.

## Full-read audit findings (2026-08-02)

Every source file (286 Python · 295 TS/TSX · 6 Go = 587) was read in full to re-verify this
doc against HEAD `9655e87`. The architecture above held up; the items below are confirmed
drift, latent defects, and dead code that were **not** previously recorded. Each was verified by
direct read (file:line), not inferred.

**Confirmed drift**
- **`deploy.yml` still requires + writes a dead `JWT_SECRET`.** The cookie-session migration
  removed all JWT code from `backend/app/` (grep: zero hits for `JWT_SECRET`/`create_access_token`/
  `decode_access_token`; `test_jwt_removed.py` asserts the settings are gone), but
  `.github/workflows/deploy.yml` still hard-fails if `secrets.JWT_SECRET` is unset (L19) and writes
  `JWT_SECRET=…` into the prod `.env` (L37). The backend never reads it — harmless but dead config;
  a future cleanup should drop the check + the `.env` line.

**Latent defects (verified, not yet fixed)**
- **`PATCH /messages/{id}/rating` is unauthenticated at the handler and double-counts.**
  `routers/messages.py:26` `update_rating(message_id, body)` takes **no `Depends`** — it imports
  `require_admin`/`get_current_user` but wires neither; access is gated only by the global
  allowlist's `_MESSAGE_RATING_PATH` (basic-user allowed). Worse, `messages.py:41-49` **always
  increments** `Agency.rating_up`/`rating_down` on every call with no read/decrement of the prior
  rating, so re-rating the same message (up→down, or up→up) inflates the denormalized counters
  permanently. No idempotency guard.
- **MCP `authorization`-header redaction has a skip bug + a None-crash.** `mcp/server.py:162-165`
  redacts agency `authorization` headers from non-admins by `del agencies[index]["api_headers"][j]`
  **while iterating that same list by index** — after a delete every later element shifts down but
  `enumerate` advances `j`, so the element immediately after a redacted header is skipped. Two
  adjacent `authorization` headers → the second **leaks to a non-admin**. The safe approach
  (setting `value="REDACTED"`) is commented out directly above (L164). Also `header.get("name").lower()`
  raises `AttributeError` if a header lacks `name`.
- **Stubbed analytics return hardcoded zeros.** `routers/insight.py` `GET /analytics-insights`
  returns `totalWeekQuestions=0` (`:88`) and `HeatmapInsights.totalRequests=0` (`:236`) as literals —
  not computed. `routers/feedback.py` daily-trend `rate` is `0` (`:249`) and ~135 lines of the old
  implementation are commented out (`:86`, `:116`), though the per-agency `rate` **is** computed via
  `RawSQL('AVG(CASE WHEN rating = up …) * 100')` (`:209`) — so "feedback rate is never computed" is
  only partly true.

**Dead / orphaned code (zero importers, verified by grep)**
- Frontend chat: `features/chat/AgentStepDisplay.tsx` (and its `StreamingProgress` export) — no
  importer. The live pipeline view is `ChatConversation.tsx:37` `<AgentStepsCard defaultOpen loading>`
  fed by `buildAgentStepsSnapshot` (as this doc already states). Note two divergent `STEP_LABELS`:
  `chatHelpers.ts:27` (6, incl. `summarize`) vs the dead `AgentStepDisplay.tsx:5` (5).
- Frontend dashboard: `features/dashboard/LiveActivityChart.tsx` + `useRealtimeActivity.ts` — no
  importer (`DashboardPage` never mounts them).
- Frontend executive: `features/executive/exportExecutiveReport.ts` (jsPDF report) — no importer;
  `ExecutivePage` renders no export button, so several `ExecutiveKPIs` fields (`costSaved`,
  `agencyScorecard`, `topIssues`) exist only to feed this unused path.
- Frontend public: `AgencyCards.tsx` `agencyColors`/`agencyBgColors` are keyed by slugs
  (`fda`/`revenue`/…) but the lookup key is the agency **UUID** `id`, so the tint never applies
  (a test explicitly guards the fallback).
- `llmRouteApi.ts` `createRoute`/`deleteRoute`/`listPurposes` — all exported, none used (RoutesPanel
  is edit-only, as recorded). Backend unused imports: `mcp/server.py`/`main.py` import
  `generate_uuid`/`now` partly unused; `utils/uuid7.py` imports `os` unused.

**Other verified specifics worth pinning**
- **Dashboard 4× over-fetch:** `dashboardApi` fires four TanStack queries
  (stats/agencyUsage/weeklyTrend/categoryData) that all hit the single `/dashboard/stats` endpoint.
- **Auto-maintenance threshold:** `agency_reconcile` flips to maintenance only on **>50% (strict)
  error rate AND ≥5 checks** (`test_agency_reconcile.py`).
- **Tests are SQLite-`:memory:`-only** except two gated files: `services/test_similarity_window_pg.py`
  (`TEST_PG_URL`) and `test_redis_rate_limit.py` (`TEST_REDIS_URL`, skips if unreachable). RBAC
  matrix (`test_surface_parity.py`) walks the **real** `app.routes` table, not a hand list.
- **Test coverage gaps:** no end-to-end MCP-over-HTTP authz test (MCP role behavior is verified only
  by reproducing the DB lookup + a source-inspection guard `test_mcp_role_access.py:128`); the
  `scripts/hash_existing_api_keys.py` migration is itself untested; no full live-upstream WS chat-turn
  test (streaming upstream is always stubbed).
- **Responses translate emits ~10 of 53 events** (the 8-event answer burst + `response.created` +
  `response.completed`/`response.failed`) — this doc's "9" counts the happy path + `failed`; the
  extra is the `created` lifecycle event. `usage` is always zero by design; `input_items` ignores its
  `order`/`limit` args (`responses/retrieve.py:57`).

## 2026-08-02 — frontend/index.html SEO + OG rebrand

- Replaced Lovable placeholder metadata in `frontend/index.html` with real branding + full SEO/social
  tags: `<html lang="th">`, Thai `<title>`/`description`/`keywords`/`author`, `robots`,
  `theme-color`, `canonical`, and complete `og:*` / `twitter:*` sets (incl. `og:image:width/height/alt`).
- **Public title is now `ศูนย์บริการข้อมูลภาครัฐ`** in the meta tags and the OG image (per user choice).
  Note this diverges from the in-repo product name "AI Chatbot Portal" / "Thai Citizen Guide" —
  the divergence is intentional for the public link preview only; app UI/`APP_NAME` unchanged.
- Canonical + `og:image` absolute URLs point at prod `https://chatbotportal.opdc.ai.in.th/`.
- Added `frontend/public/og-image.png` (1200×630) — "Style 6" chat-card design, rendered from a
  scratchpad HTML mock via headless Chrome. Old Lovable R2 preview image reference removed.

## 2026-08-02 — Standalone Go MCP server at /mcp-v2

- New top-level `mcp-server/` service (module `github.com/willywotz/thai-citizen-guide/mcp-server`),
  built on the official `go-sdk v1.7.0`, exposing a streamable-HTTP MCP endpoint with `Stateless: true`.
  It targets strict MCP `2026-07-28` conformance: the latest protocol version is advertised only via
  the SEP-2575 `server/discover` RPC, while the legacy `initialize` handshake reports compat
  capabilities pinned at `2025-11-25` (verified empirically below — this is expected, not a bug).
- Reads Postgres **directly via `pgx`** (`store.go`), the same pattern as `agent-proxy`; it does not
  import the Python `backend` package. It re-implements, in Go: sha256 API-key auth (`auth.go`),
  admin-only header redaction and `API`→`/agent-proxy/{id}` endpoint-URL rewrite
  (`agencies.go`/`url.go`), and `__user_id__`/`__conversation_id__` payload templating — mirroring
  `backend/app/mcp/server.py`'s `list_agency` tool.
- Deploy is purely additive: the old Python `/mcp` (served by `backend`) is untouched; the new
  service is reachable at `/mcp-v2` via an nginx `^~ /mcp-v2` location (`nginx/routes.conf`) plus a
  new `mcp-server` compose service (`docker-compose.yaml`) — no existing routes or services changed.
- **Parity check (Task 10), stack `postgres`+`postgres-init`+`backend`+`mcp-server`+`nginx` up via
  `docker compose`, called `list_agency` from the backend container's `fastmcp` client against both
  `http://backend:8080/mcp/` and `http://mcp-server:8080/mcp-v2`:**
  - **Protocol fact confirmed:** a classic `fastmcp.Client` (raw `initialize`) negotiates
    `protocolVersion=2025-11-25` against **both** servers — expected, since `initialize` is
    deprecated in `2026-07-28` and the newer version is only offered via `server/discover`.
  - **Data identity matches:** the seeded DB has 4 agencies (FDA/MCP, กรมสรรพากร/API,
    กรมการปกครอง/A2A, กรมที่ดิน/MCP). `/mcp-v2` returned all 4 with `id`/`name`/`connection_type`/
    `data_scope` exactly matching a direct `SELECT` against `agencies`, and correctly rewrote the
    `API`-type agency's `endpoint_url` to the `/agent-proxy/{id}` form.
  - **Discrepancy found (pre-existing Python bug, not introduced by this work):** `/mcp`'s
    `list_agency` tool call **crashes** (`fastmcp.exceptions.ToolError: 'NoneType' object has no
    attribute 'items'`) on the current seed data, because `backend/app/mcp/server.py:170` does
    `agency["expected_payload"].items()` unconditionally, and the seeder never sets
    `expected_payload` (column is `NULL` for all 4 rows; `Agency.expected_payload` is
    `JSONField(null=True)`). `/mcp-v2` handles the same `NULL` gracefully, returning `{}`. This is a
    **new latent defect** (Python-side, out of scope for the Go server / this task to fix) — added
    here for visibility alongside the existing "Latent defects" list earlier in this doc. Net
    parity verdict: the two servers read identical agency data from Postgres; the Go server is
    strictly more robust against `NULL expected_payload` than the Python original, which currently
    cannot serve `list_agency` at all against the present seed data.
- Final sweep in `mcp-server/`: `go test ./...` → 13 passed; `go vet ./...` → clean; `go build ./...`
  → success.
