# Platform Roadmap Spec — AI Chatbot Portal

Status: proposal (draft)
Scope: what to add, what to remove, and what to consolidate to make this a
production-grade LLM gateway + a healthy ecosystem for agencies, citizens, and
operators.

Context: the system today is an AI Orchestrator (OneChat-compatible) that
routes citizen questions to government agencies over API / MCP / A2A, plus an
admin dashboard. This spec builds on the OneChat specs in `spec/` and the
current backend (`backend/app`), agent proxy (`agent-proxy/`), and frontend
(`frontend/src/features/`).

---

## 0. Security & hygiene — do before any new feature

### 0.1 Rotate exposed credentials

`spec/agent-onechat.md` and `spec/agent-promes.md` contain real API keys
(OpenRouter, OpenAI, Dify). They are gitignored (`spec/.gitignore` →
`agent-*.md`) so they are not in git history, but they have been shared in
chat threads. Rotate all three keys and replace the values in local notes
with `<REDACTED>`.

### 0.2 Hash user API keys

`UserAPIKey.key` (`backend/app/models/user.py`) is stored in plaintext and
compared directly.

- Store only `sha256(key)`; show the raw key once at creation.
- Add `key_prefix` (first 8 chars) for display, and `last_used_at` for audit.
- Migration: hash existing keys in place (they keep working; they just become
  unreadable, which is the point).

### 0.3 Redact connection log bodies (PDPA)

`ConnectionLog.request_body` / `response_body` store full payloads — citizen
questions and possibly auth headers in plaintext.

- Strip `Authorization` and api-key headers before persisting.
- Truncate bodies to a configurable limit (e.g. 4 KB).
- Add a retention job: delete logs older than `CONNECTION_LOG_RETENTION_DAYS`
  (default 90). The scheduler service already exists — add one more job.

### 0.4 Enforce a real `JWT_SECRET` in production

Refuse to start when `ENV=production` and `JWT_SECRET` is the default value.

---

## 1. Gateway core — features the gateway must have

Priority order: 1.1 → 1.2 → 1.3 → 1.4 → 1.5. Each builds on the previous.

### 1.1 Token & cost tracking

OpenRouter already returns `usage` (prompt/completion tokens) in every
response; we currently discard it.

- New columns on `ConnectionLog` (or a new `llm_usage` table):
  `model`, `prompt_tokens`, `completion_tokens`, `cost_usd`.
- Record usage for every LLM call: router, synthesis, parse-spec, embedding.
- Expose:
  - `GET /api/v1/insight/usage?group_by=user|agency|model|day`
  - a "Cost" card on `DashboardPage` and a per-model breakdown view.

### 1.2 Rate limiting (currently a dead field)

`Agency.rate_limit_rpm` exists but nothing enforces it.

- Enforce per-agency RPM in the dispatch path
  (`backend/app/services/chat/dispatch.py`) with a sliding-window counter.
- Add per-API-key and per-user limits (config default + per-key override).
- On limit: respond `429` with `Retry-After` and the standard error envelope
  (see 1.5).

### 1.3 Quotas & budgets

Once usage is tracked (1.1), enforce it:

- Per-user / per-API-key monthly token or USD budget
  (`quota_tokens_month`, `quota_usd_month`, nullable = unlimited).
- Global daily budget kill-switch (protects the OpenRouter account).
- On exceeded quota: `429` + error envelope; show usage bar on `ApiKeysPage`.

### 1.4 Retry, backoff, circuit breaker

All upstream calls are single-attempt httpx with a timeout.

- Retry transient failures (connect errors, 429, 5xx) with exponential
  backoff, max 2 retries, only for idempotent dispatches.
- Circuit breaker per agency: N consecutive live-traffic failures → trip the
  existing `auto_maintenance` flow (today only health probes do this).
  Half-open probe after cooldown re-activates.

### 1.5 One error envelope everywhere

Today errors come back in different shapes (OneChat `data.errors[]`, FastAPI
`detail`, ad-hoc strings). Define one:

```json
{
  "error": {
    "code": "agency_timeout",        // stable, machine-readable
    "message": "Agency X timed out after 60s",
    "upstream_status": 504,           // optional
    "retryable": true
  }
}
```

- Stable code list: `invalid_request`, `unauthorized`, `quota_exceeded`,
  `rate_limited`, `agency_unavailable`, `agency_timeout`, `llm_error`,
  `internal`.
- Keep OneChat v1/v3 response shapes unchanged for compatibility; apply the
  envelope to all `/api/v1/*` endpoints and map internal error types onto it.

### 1.6 Cache TTL & invalidation

The similarity cache (`backend/app/services/similarity.py`) never expires —
dangerous for government information that changes.

- Ignore cached answers older than `SIMILARITY_CACHE_TTL_DAYS` (default 30).
- Invalidate cached answers tied to an agency when that agency's config or
  spec changes.
- Admin "flush cache" action on `SettingsPage`.

### 1.7 Tests in CI

`.github/workflows/deploy.yml` deploys without running anything. Add a `test`
job (pytest + `go test` + frontend typecheck) that gates the deploy job.
Highest value-per-line change in this whole spec.

---

## 2. Ecosystem — features that make this a platform, not just an app

The ecosystem has three audiences: **agencies** (data providers), **citizens /
client apps** (consumers), and **operators** (admins). Grow each side:

### 2.1 Agency self-service onboarding

Today an admin creates every agency by hand via `AgencyWizardPage`.

- Agency-owner role (`role=agency_owner`, linked to one or more agencies).
- Self-service flow: register → submit endpoint + spec (reuse
  `parse-spec` + `test-connection` + `mcp/discover`) → status `draft` →
  admin approves → `active`. The lifecycle state machine already exists.
- Agency owners see only their own agency detail, health history, connection
  logs, and ratings.

### 2.2 Conformance test suite ("agency certification")

Extend `POST /agencies/test-connection` into a battery:

- responds within timeout; handles Thai text; returns non-empty answer;
  survives 3 concurrent requests; correct error behavior on garbage input.
- Store results as a scored report on the agency; require a passing run
  before `draft → active`. Surfaced in the onboarding flow (2.1).

### 2.3 Integration kit for agencies

Make "how do I connect my agency" a 30-minute task:

- One published doc: connection contract (request/response shape per
  API / MCP / A2A), timeout expectations, health-probe behavior.
- A reference agency implementation (small FastAPI app) in `examples/`.
- This replaces scattered knowledge in `spec/mcp-server.md` and tribal knowledge.

### 2.4 Notifications & status

- Email agency owners on `auto_maintenance` transitions (email service
  already exists) and on conformance failures.
- Public status page (no auth): per-agency uptime from existing health
  history. Builds trust with both citizens and agencies.

### 2.5 Quality loop (evaluation harness)

Ratings exist (`rating_up/down`) but nothing closes the loop.

- Golden question set per agency (10–20 Q with expected topics).
- Scheduled regression run (reuse scheduler): score answers via LLM-judge,
  trend per agency over time.
- Surface low-rated / failing answers to the owning agency on their
  dashboard (2.1). This is the feature that actually improves answer quality
  over time.

### 2.6 Authorization model — ReBAC + ABAC overlay on RBAC

Today authorization is pure RBAC with two roles (`user` | `admin`) enforced by
`require_admin()` / `get_current_user()` scattered across routers, plus ad-hoc
`user_id` filters in queries. That breaks down the moment `agency_owner`
(2.1) exists: "owner of *this* agency" is a relationship, not a role.

Keep RBAC as the base layer, overlay two more:

**Layer 1 — RBAC (exists, keep).** `User.role`: `user`, `agency_owner`,
`admin`. Roles grant broad capability classes (admin bypasses lower layers).

**Layer 2 — ReBAC (new).** Relationship tuples, Zanzibar-style but minimal —
one table, no extra service:

```
relationship(subject_type, subject_id, relation, object_type, object_id)
-- ('user', <uuid>, 'owner',  'agency',       <id>)
-- ('user', <uuid>, 'viewer', 'agency',       <id>)
-- ('user', <uuid>, 'owner',  'conversation', <uuid>)
```

Existing implicit relationships migrate into this model (or stay as FK checks
behind the same interface): `Conversation.user_id`, `UserAPIKey.user_id`.
New explicit ones: agency ownership for 2.1.

**Layer 3 — ABAC (new).** Attribute conditions evaluated after a relationship
match; deny overrides allow. Conditions read attributes of the subject,
resource, and environment — no new storage needed:

- subject: `user.is_active`, key scopes, quota state (1.3)
- resource: `agency.status` (e.g. owners may edit `draft`/`maintenance` but
  not `active` without admin approval), log age (older than retention →
  nobody but admin)
- environment: global kill-switch (1.3)

**Single decision point.** One function in `backend/app/auth/authz.py`:

```python
async def authorize(subject: User, action: str, resource: Any) -> Decision:
    # 1. RBAC: admin → allow; role lacks capability → deny
    # 2. ReBAC: required relation exists for (subject, resource)?
    # 3. ABAC: all attribute conditions pass? deny overrides
```

Actions are coarse verbs per resource type: `agency:read|edit|delete|
change_status`, `conversation:read|delete`, `connection_log:read`,
`settings:edit`, `user:manage`. Routers call `authorize()` (as a FastAPI
dependency) instead of `require_admin` + inline filters. List endpoints get a
companion `scope_query(subject, action, queryset)` that pushes the same rules
into the DB query instead of filtering in Python.

Example matrix:

| Action | user | agency_owner | admin |
|---|---|---|---|
| `agency:read` (active) | allow | allow | allow |
| `agency:edit` | deny | ReBAC `owner` + ABAC `status != active` | allow |
| `agency:change_status` | deny | deny (admin approves) | allow |
| `connection_log:read` | deny | ReBAC `owner` of agency | allow |
| `conversation:read` | ReBAC `owner` | ReBAC `owner` | allow |
| `settings:edit` | deny | deny | allow |

Implementation notes:

- Build in-house first (one table + one module + tests). Adopt OpenFGA /
  Permify / Casbin only if rules outgrow this — the interface above makes
  that swap invisible to routers.
- Log every deny (and admin-bypass allow) to the audit log (section 1 /
  admin-action audit) with subject, action, resource, and which layer denied.
- TDD the decision table: one test per matrix cell, plus deny-overrides-allow
  and inactive-user cases.

### 2.7 Developer experience for API consumers

- Publish the FastAPI-generated OpenAPI doc at a stable URL, linked from the
  frontend.
- `docs/quickstart.md` with curl + Python + JS examples using a user API key.
- Per-key usage view on `ApiKeysPage` (needs 1.1).

---

## 3. Remove / consolidate — things that are messy today

### 3.1 Chat endpoint sprawl

Four entry points: `POST /chat` (alias), `/chat/internal`, `/chat/external`,
`/chat/stream`, speaking three OneChat versions (v1/v3 sync, v4 stream).

- Pick the primary public surface: **`/chat/stream` (v4 SSE)** for the UI,
  `/chat` (sync) for API consumers.
- Mark `/chat/internal` and `/chat/external` as internal-only (or fold the
  internal LangGraph path behind a flag) — do not document them publicly.
- Delete the alias indirection where `/chat` just re-calls another handler.

### 3.2 Duplicate / stale spec files — DONE

- `spec/hello.md` (duplicate of agent-onechat.md content) and `spec/readme 2.md`
  (older near-duplicate of readme.md) have been deleted.
- `spec/readme.md` renamed to `spec/mcp-server.md` (the MCP server requirements doc).
- `spec/ai-chat-api-spec.yaml` archived to `spec/archive/ai-chat-api-spec.yaml`
  (describes the pre-FastAPI Supabase Edge Functions architecture; kept for historical reference).
- `spec/InceptionReport_*.pdf` and `spec/v4-streaming.html` are now git-ignored
  (binaries/raw captures); `spec/v4-streaming.md` (distilled) stays tracked.

### 3.3 Dead or duplicated mechanisms in code

- `Agency.rate_limit_rpm`: implement (1.2) — a dead config field is worse
  than no field, because operators believe it works.
- `Message.embedding` stored as JSON text with a 50 000-char cap while
  pgvector is installed: move to a real `vector` column; similarity search
  becomes an indexed query instead of decode-and-compare.
- Agency status enum has both `disabled` and `inactive`: collapse to one
  (keep `disabled`), migrate data.
- Legacy `/mcp/` streamable-HTTP mount vs the spec-required `/sse` +
  `/messages`: keep both only while OneChat needs both; add a removal date,
  then delete the legacy mount.

### 3.4 Repo clutter

- `lab/` experiments: move to a separate branch or `lab/README.md` stating
  "not part of the product, not maintained".
- `spec/InceptionReport_*.pdf` (1.5 MB) and `spec/v4-streaming.html` (45 KB
  raw capture): git-ignored (untracked from index, still on disk); `spec/v4-streaming.md`
  (distilled) stays tracked. DONE.

### 3.5 Things deliberately NOT to build (avoid scope creep)

- Multi-LLM-provider abstraction / load balancing — OpenRouter already is
  that layer.
- API v2 / versioning machinery, webhooks with HMAC signing — premature
  until there are external consumers who need them.
- A `/models` discovery endpoint — model choice is internal config; no
  consumer exists.

---

## 4. Suggested build order

| Phase | Items | Why first |
|---|---|---|
| 1 | 0.1–0.4, 1.7 | security + CI safety net, all small |
| 2 | 1.1, 1.2, 1.3 | cost visibility → enforcement; protects budget |
| 3 | 1.4, 1.5, 1.6 | reliability + clean API contract |
| 4 | 3.1–3.4 | consolidation (cheaper after envelope exists) |
| 5 | 2.6, 2.1, 2.2, 2.3 | authz model first, then agency self-service on top |
| 6 | 2.4, 2.5, 2.7 | quality loop + public trust |

Each phase is independently shippable; stop after any phase and the system is
still better than before.
