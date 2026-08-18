# Methodology-compliance assessment — 2026-08-18

Scores the backend against the four mandated rules after a full-read re-audit at HEAD. Every
finding was verified by direct read (`file:line`), not inferred. Supersedes the
`2026-08-17` assessment, which predates the Clean-Architecture router sweep, the route renames,
and the EDA outbox — this one reflects that remediated state and finds what remains.

Remediation plan: `docs/superpowers/plans/2026-08-18-methodology-compliance-remediation.md`.

## Verdict

| Rule | Verdict | Core issue |
|---|---|---|
| Full-English route names | Near-compliant | 3 short-form segments remain (`stats`, `info`, `spec`) |
| Clean Architecture | Partial | Routers clean; **15 service modules depend on FastAPI** |
| Event-Driven Architecture | Seam only | Correct outbox, but 1 producer / 1 consumer; ~95% of state changes imperative |
| 15-Factor | Strong | One documented exception (VI uploads) + minor dead config |

---

## Rule — Full-English API route names

Compliant across the surface; the recent renames landed (`/authentication`, `/language-model`,
`/anonymous`, `/connection-logs`, `/popular-questions`, `/executive-summary`, `/agency-health`,
`/usage-heatmap`).

**3 remaining violations** — short forms of ordinary English words (the class the rule targets):

| Route | `file:line` | Fix |
|---|---|---|
| `GET /dashboard/stats` | `routers/dashboard.py:14` | `stats` → `statistics` |
| `GET /feedback/stats` | `routers/feedback.py:25` | `stats` → `statistics` |
| `GET /connection-logs/info` | `routers/connection_logs.py:98` | `info` → `information` |
| `POST /agencies/parse-spec` | `routers/agencies/spec.py:29` | `spec` → `specification` |

**Correctly exempt (leave as-is):** the OpenAI external contract — `/responses`, `/conversations`,
`/items`, `/input_tokens`, `/input_items`, `/compact`, `/cancel` (renaming breaks SDK
compatibility; the snake_case is OpenAI's wire spelling); the protocol proper noun `/mcp/discover`;
and `/api-keys` ("API" is the standard term). These match the documented CONTEXT.md decisions.

---

## Rule — Clean Architecture

**Holds:** routers build **zero ORM querysets** — the only ORM-looking hit under `app/routers`
was a false positive (`api_key_service.create(...)`, a service call at `api_key.py:66`). The
2026-08-17 "no queryset in any router" refactor is intact.

**Minor:** 23 routers import `app.models`, but almost all import only `User` to type
`Depends(get_current_user)`; the few naming data models (`AuditLog`, `ConnectionLog`,
`LlmProvider/Route`, `Conversation`, `Agency`) use them for `response_model`/typing, not queries
(verified — no `.filter/.get/.create` on them in routers). Tolerable under the Active-Record
pattern (the models *are* the domain entities).

**Violation — the dependency rule points inward the wrong way.** 15 service modules import the
web framework:

- `HTTPException`/`status` (12): `services/agency.py`, `agency_golden.py`, `agency_lifecycle.py`,
  `agent_proxy.py`, `api_key.py`, `connection_log.py`, `conversation.py`, `feedback.py`,
  `llm/admin.py`, `message.py`, `popular_questions.py`, `user.py`
  (e.g. `services/conversation.py:114` `raise HTTPException(404…)`,
  `services/llm/admin.py:42` `raise HTTPException(409…)`).
- `BackgroundTasks` (2): `services/chat/stream.py`, `services/chat/aggregate.py`.

The use-case layer knows HTTP status codes and the framework's scheduling primitive. **Fix
(pattern already in-repo):** raise domain errors — `ApiError` (`app/errors.py`), `LlmError`,
`OneChatError`, `ConversationNotFound` — and translate at the router/global handler; inject a
scheduling port (or reuse `spawn_logged`, `app/concurrency.py`) instead of `BackgroundTasks`.
Behavior is unchanged — the global handlers already emit an identical envelope for `ApiError`
and `HTTPException`, so this is purely structural.

---

## Rule — Event-Driven Architecture

**Design is correct** — a real transactional outbox: `services/events.py`
(`publish` → `DomainEvent` row enlisted in the caller's transaction; `dispatch_pending`
at-most-once), `event_consumers.py` (`subscribe`), wired into the scheduler
(`scheduler.py:113-114`).

**Coverage is minimal — a seam, not an architecture:**
- 1 producer: `agency_lifecycle.py:35` `publish("agency.status_changed", …)`.
- 1 consumer: `event_consumers.py:28` → audit projection.
- Everything else changes state imperatively: **17** direct `record_audit(...)`, **30** counter
  mutations (`rating_up/down`, `total_calls`/`increment_calls`), **4** direct `ConnectionLog`
  writes, plus cache-flush and classification.

So ~1 of ~20 domain state-changes is event-driven. The repo **explicitly chose YAGNI** here
(CONTEXT.md: "a broker only when a second service must consume the stream"). Strict compliance
would model state changes as events with side effects as consumers — a large, behavior-touching
change. See the plan's Phase 4 decision gate.

---

## Rule — 15-Factor

Strong. Evidence per factor:

| Factor | Status | Evidence |
|---|---|---|
| II Dependencies | Pass | `backend/uv.lock`, `frontend/pnpm-lock.yaml` |
| III Config | Pass (1 nit) | pydantic-settings + DB overrides; `main.py:23` reads `os.getenv("LOG_LEVEL")` directly (bootstrap ordering — duplicates the config field) |
| IV Backing services | Pass | all by URL (`DATABASE_URL`, `ONECHAT_BASE_URL`, `MCP_ENDPOINT_URL`, OpenRouter/ThaiLLM); Redis removed |
| VI Stateless processes | Exception | agency-logo uploads on a local volume `UPLOAD_DIR` (`routers/agencies/logo.py:45`) — documented deliberate exception (single-node; S3/MinIO upgrade path recorded). Also the per-worker LLM route cache: `invalidate()` (`llm/client.py:61`) clears only the calling worker → ≤30s staleness across `--workers 4` (minor eventual-consistency) |
| XI Logs | Pass | `logging.basicConfig(stream=sys.stdout…)` in `main.py` |
| XII Admin processes | Pass | `scripts/seed.py`, `scripts/hash_existing_api_keys.py` |
| V / IX / X | Pass | Docker multi-stage, tag-driven release, `compose.override` dev parity |

**Residual dead config:** unused `python-jose` dep (`backend/pyproject.toml:26`) and dead
`JWT_SECRET`/`JWT_ALGORITHM` in the frontend `RESTART_FIELDS`
(`features/settings/SettingsPage.tsx:15`).

---

## Prioritized remediation (see plan for steps)

1. **Clean Architecture** — strip FastAPI out of the 15 service modules (clearest strict
   violation, mechanical, well-tested). *Phase 1.*
2. **Route names** — 3 renames, each backend + frontend caller + parity test in one commit.
   *Phase 2.*
3. **15-Factor nits** — drop `python-jose`, remove dead frontend JWT fields. *Phase 3.*
4. **EDA** — decision gate; expand only if strict compliance is judged to override the
   documented YAGNI stance. *Phase 4.*
