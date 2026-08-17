# Comment cleanup plan

Audit of every comment and docstring across the codebase (backend `app/` + `tests/`, frontend `src/`). Each item is categorized as **NOISE** (remove), **KEEP** (essential — explains WHY), or **REFACTOR** (the comment exists because the code is unclear; fix the code so it self-documents).

**Totals:** ~250 NOISE · ~290 KEEP · ~15 REFACTOR, across ~614 files.

The KEEP set is large and high-quality — this codebase comments for the right reasons (security invariants, external-service quirks, regulatory reasons like PDPA, deliberate-simplification `withinlazy:` markers, cross-stack mirroring, async/ORM quirks). **Do not touch KEEP.** This plan only acts on NOISE and REFACTOR.

Execution is mechanical and low-risk for NOISE; REFACTOR items need a code change + test run.

---

## Phase 1 — Dead code & stale comments (highest priority, zero risk)

Pure deletion. Nothing depends on these.

| File:line | Item | Action |
|---|---|---|
| `backend/app/mcp/client.py:7-35` | Entire file: commented-out http/sse transport blocks + pasted `CallToolResult` output dump | Delete the dead blocks (keep only live code). Largest single noise source. |
| `backend/app/config.py:151,153,154` | Dead commented-out `SETTINGS_GROUPS` entries | Delete. |
| `backend/app/database.py:10` | `# print((await command.history())[-1])` dead debug print | Delete. |
| `backend/app/main.py:94` | `# await seed_popular_questions()` dead disabled call | Delete (or document why it's disabled — but no rationale exists). |
| `backend/app/mcp/server.py:164` | `# agencies[index]["api_headers"][j]["value"] = "REDACTED"` dead alternative | Delete; add a real one-line WHY on the `del` above if the security reason isn't clear. |

**Stale (inaccurate, not just redundant) — fix the wording or delete:**

| File:line | Issue | Action |
|---|---|---|
| `backend/app/errors.py:1-5` | "stable codes" list cites phantom codes (`quota_exceeded`, `llm_error`) and omits real ones | See REFACTOR below — extract codes to an `Enum`. |
| `backend/app/config.py:216` | References nonexistent `register_tortoise` | Delete the comment. |
| `backend/app/auth/dependencies.py:53-57` | Says "JWT" but JWT auth was removed | Replace "JWT" → "credential"/"API key". |
| `backend/app/models/user.py:17` | `# user | admin` omits `staff` | Fix to `# user | staff | admin` (or REFACTOR to a `Literal`/enum). |
| `backend/app/models/user.py:36-39` | `UserAPIKey` docstring claims per-key "permissions" no field backs | Delete the false claim. |
| `frontend/src/features/agencies/useAgencies.ts:159` | Typo "ag ency" | Delete (the comment restates `invalidateQueries`). |

---

## Phase 2 — Mechanical NOISE removal (bulk, low risk)

Patterns repeated across many files. Each is a pure deletion that does not change behavior.

### 2a. Section-divider banners (`# --- X ---`, `// --- X ---`)

Restate the function/type/route they sit above. Remove everywhere:

- **Backend:** `routers/agencies/__init__.py:21-34` (10 route-path restatements), `routers/auth.py:61-149` (six `# Login`/`# Logout`/… dividers), `routers/llm.py:76,85,151`, `routers/connection_logs.py:10`, `routers/conversations.py:87`, `models/agency.py:33,52,68,74,77,82`, `schemas/agency.py:10,32,53,61,68`, `schemas/conversation.py:10,46,93,126`, `schemas/insight.py:5,11`, `auth/security.py:12,28` (tiny file), `services/seed.py:70`, `services/chat/dispatch.py:29,130`, `services/analytics/brief.py` (n/a), `config.py` dividers (KEEP — file is large enough to earn them).
- **Frontend:** `agencyForm.ts`, `agencyForm.test.ts`, `agencySchema.ts`, `agencySchema.test.ts`, `useAuth.tsx`, `apiClient.ts`, `status.ts`, `chatHelpers.test.ts`, `useChat.test.tsx`, `ApiKeysPage.test.tsx`, `chatApi.ts:45,209` — the `// --- X ---` banners.
- **Backend tests:** `services/test_popular_questions.py:22,43,122,124,400,402`, `services/test_chat_turn.py:49,89`, `services/test_dispatch.py:9,306`, `routers/test_chat_stream_v5_fields.py:78,139`, `routers/test_responses_ws_route.py:77`, `test_conversations_history.py:75`, `test_users_service.py:80`.

### 2b. Docstrings that restate the function/class name

`"""Return one agency or raise 404."""` on `get_agency_or_404`, etc. Remove the docstring (the name + signature already say it). Examples:

- **Backend:** `services/agency.py:32,42`, `services/user.py:26,57,94,131`, `services/connection_log.py:1`, `services/conversation.py:1-4,20`, `services/message.py:1-4`, `services/feedback.py:1-4`, `services/settings.py:1-3`, `services/auth_session.py:1`, `services/mcp_discovery.py:1`, `services/agency_golden.py:1`, `services/agency_lifecycle.py:22`, `services/rate_limit.py:64,115`, `services/openai/conversations.py:1`, `services/responses/continuity.py:45`, `services/responses/request.py:1`, `services/responses/session.py:28`, `services/onechat/client.py:30`, `services/analytics/heatmap.py:1`, `services/analytics/brief.py:104`, `routers/agencies/_utils.py:1`, `routers/agencies/golden.py:1`, `routers/agencies/lifecycle.py:1`, `routers/agencies/spec.py:1`, `routers/audit_log.py:1`, `routers/messages.py:1`, `routers/users.py:1`, `routers/dashboard.py:1` (noise part), `app/database.py:6,19`, `app/main.py:182`, `app/auth/security.py:1-3`, `app/utils/retry.py:1`.
- **Frontend:** `chatHelpers.ts:88,116,127`, `AssistantMessageContent.tsx:11`, `apiKeyApi.ts` (n/a), `chart.tsx:277`.
- **Pydantic `XxxCreate`/`XxxUpdate`/`XxxListResponse`/`XxxResponse` docstrings** that only restate the class name: `schemas/agency.py:76,81,108,121`, `schemas/llm_provider.py:24,29,62`, `schemas/llm_route.py:20,25,49`, `schemas/popular_question.py:25`. (Keep the ones with a real WHY, e.g. `llm_provider.py:44` "api_key is always masked".)

### 2c. Inline comments that restate the adjacent code

- **Backend:** `services/agency_health.py:52` (`# ascending by created_at`), `services/agent_proxy.py:54` (`# W3C trace context`), `services/connection_log.py:57` (`# Check if agency exists`), `services/llm/admin.py:51` & `services/llm/client.py:72` (`# lazy FK load`), `services/message.py:44` (`# If agency not found, skip`), `services/similarity.py:100`, `config.py:50` (`# 7 days`), `config.py:52` (`# old sid stays valid…`), `auth/ws.py:20` (`# header decides`).
- **Frontend:** `ChatPage.tsx:18`, `chatApi.ts:154,191,201`, `useChat.ts:42,56`, `useRealtimeActivity.ts:28,43,65,76`, `exportExecutiveReport.ts:12,26,55,79,107`, `exportHistory.ts:34`, `ApiKeysPage.tsx:30,56,75,93`, `PopularQuestionsPage.tsx:37,49,62,82`, `sidebar.tsx:81`, `menu.tsx:202`, `context.tsx:27,40,46,51,64`.
- **Backend tests:** `test_analytics.py:114,138,251,336-343`, `test_rate_limit.py:90,95-98,108`, `test_llm_client_chat.py:34`, `test_llm_client_queue.py:12,17,38`, `test_mcp_role_access.py:84,87,115,119,123`, `test_message_no_embedding.py:9`, `test_audit.py:30`, `test_audit_endpoint.py:18`, `test_auth_change_password.py:40`, `test_basic_user_allowlist.py:153,158`, `test_cache_flush.py:9,14`, `test_conversation_ownership.py:20`, `test_public_agencies.py:29`, `test_test_connection_reset.py:43,83`, `test_agent_proxy_trace_query.py:41`, `test_config_overrides_report.py:10-12`, `test_users_service.py:55,70,77,92`, `test_auth_session.py:35,66-67`, `test_similarity_join.py:140,169`, `routers/test_auth_anon.py` (n/a), `routers/test_openai_conversations.py:101`.
- **Frontend tests:** `editTabs.test.tsx:86,155,158`, `wizardFlow.test.tsx:34,63,68,72,82,87,109`, `ApiKeysPage.test.tsx:140,153,277`, `AuditLogPage.test.tsx:67,74,77,168,174`, `HistoryPage.test.tsx:48,51,81,84,89,92,102,110,122,165`, `chatRatingFlow.test.tsx:22,36`, `useChat.test.tsx:40,55,85,87,98,101,116,193,226,243`, `chatHelpers.test.ts:143,383,511-562`, `chatApi.test.ts:76,87,90,95`, `FeedbackSummaryCards.test.tsx:34`, `HealthPage.test.tsx:47`, `ConnectionLogsTable.test.tsx:53`.

### 2d. Test docstrings that restate the test function name

e.g. `def test_cache_hit_returns_ids` + `"""Cache hit: returned tuple ids match…"""`. Bulk-remove the docstring; the name already describes the scenario. Worst offenders:

- `services/test_similarity_join.py` (8 such docstrings), `routers/test_responses_http.py:34,64,92,235`, `routers/test_responses_ws_route.py:94,139`, `routers/test_executive_summary.py:18,27,37`, `routers/test_chat_stream_v5_fields.py:51,151`, `routers/test_chat_stream_upstream.py:48,68`, `services/test_analytics.py:138,155,187,251,292`, `test_mcp_role_access.py:39,48,57,64`, `test_mcp_sse_transport.py:21,26,35`, `test_mcp_stateless_http.py:20,28`, `test_mcp_streamable_calls.py:66,83`, `test_basic_user_allowlist.py:36,64,158`, `test_staff_allowlist.py:158`, `test_surface_parity.py:25,44,141`, `test_agency_reachability.py:74`, `test_conversations_history.py:79`.

---

## Phase 3 — REFACTOR (code change so the comment is unnecessary)

These are the cases where a comment exists *because the code is unclear*. The fix is to make the code self-document, then delete the comment. Each needs a code change + `pytest`/`pnpm test` run.

### 3a. Closed-set `str` fields → `Literal` (backend)

Closed value lists held as `# a | b | c` comments on `str`/`CharField`. Make them `Literal[…]` (schemas) — enforced + self-documenting.

| File:line | Field | Values |
|---|---|---|
| `schemas/agency.py:37` | `state: str` | `up \| degraded \| down \| unknown` |
| `schemas/conversation.py:17` | `role: str` | `user \| assistant` |
| `schemas/conversation.py:42` | `rating: str` | `up \| down` |
| `routers/agencies/lifecycle.py:29` | `status` | `done \| error` |
| `routers/agencies/lifecycle.py:42` | `protocol` | `REST API \| MCP \| A2A \| UNKNOWN` |

(Tortoise `models/` uses plain `CharField` with value-list comments — leave as KEEP for now; migrating those to `CharEnumField` is a separate, larger pass.)

### 3b. Unit-less / vague names → rename

| File:line | Now | Rename to | Why |
|---|---|---|---|
| `routers/agencies/lifecycle.py:31` | `time` (`# milliseconds`) | `time_ms` | matches `latency_ms` convention in `connection_logs.py` ⚠️ API contract change |
| `frontend/src/features/agencies/ConnectionTestResult.tsx:7-8` | `status: string`, `time` (`# ms`) | `status: 'done' \| 'error'`, `timeMs` | type self-documents |
| `frontend/src/features/api-keys/apiKeyApi.ts:17` | `key` (`# full key — shown once`) | `plaintextKey` | once-only contract in the name |
| `frontend/src/shared/data/mockData.ts:4` | re-export comment | finish the type-re-export migration; delete the re-export + comment | migration debt |

### 3c. Magic numbers → named constants

| File:line | Now | Refactor |
|---|---|---|
| `backend/app/config.py:93` | `EVAL_INTERVAL_HOURS=168  # weekly` | `168` → `7 * 24` |
| `frontend/src/features/agencies/wizard/wizardFlow.test.tsx:39` | inline invalid URL string | extract `INVALID_URL_NO_SCHEME` const |

### 3d. Self-documenting structure

| File:line | Now | Refactor |
|---|---|---|
| `backend/app/errors.py:1-5` | stale hand-maintained "stable codes" list | extract error codes to an `Enum`/module constants; drop the list (keep one-line envelope description) |
| `backend/app/services/agency.py:54` | `_full_payload` needs a docstring | rename → `_flatten_agency_payload` |
| `frontend/src/features/agencies/useAgencies.ts:161` | `# matches ['connection-logs', agencyId, …]` | extract `connectionLogKeys.list(agencyId)` query-key factory |
| `backend/tests/services/test_analytics.py:303-318` | `# currentLatency` / `# avgLatency` labels on a `side_effect` list | build the side_effect as a dict keyed by query name |
| `backend/tests/services/test_analytics.py:41-43` | inline `_FakeQuerySet` mock class | extract to a shared named test helper |
| `backend/tests/services/test_rate_limit.py:95-98` | `# fail 1`/`# recover` narration | use descriptive locals (`first_failing = await …`) |

---

## Phase 4 — KEEP (do not touch)

Not an action — a guardrail. The following are essential and must survive any cleanup. Representative high-value items:

- **Security/trust-boundary:** `main.py:161-169` (MCP mount bypass intent + test ref), `auth/dependencies.py:176/181/187/263-266` (auth precedence, 401-vs-403, migration safety), `auth/security.py:25` (unusable hash never authenticates), `auth/ws.py:1-8,38-39` (CSWSH defense), `routers/responses.py:184` (socket cap DoS mitigation), `routers/agencies/logo.py:34` (SVG XSS exclusion), `models/audit.py:10-12`, `schemas/llm_provider.py:44` (api_key masked).
- **External-service quirks:** `mcp/server.py:80-86,98-101`, `trace_util.py:1-6`, `main.py:171-173,194-197`, `onechat/client.py:16-18,20,132-137`, `responses/translate.py:152-153`, `similarity.py:53,66` (Postgres vs SQLite placeholders).
- **Async/ORM/concurrency:** `concurrency.py:13-17` (asyncio GC), `chat/stream.py:40-42` (task GC), `rate_limit.py:25-31,59-62` (lock-free invariant + Tortoise quirk), `auth_session.py:23-24` (`withinlazy:`), `events.py:35-40` (`withinlazy:` at-most-once).
- **`withinlazy:` markers** — all of them are KEEP by definition.
- **Spec/cross-stack:** `chat/aggregate.py:1-6`, `chat/pipeline_snapshot.py:1-6`, `agency_lifecycle.py:1`, `responses/continuity.py:1-7`, `responses/errors.py:1-6`, `schemas/responses.py:1-6,20,22,24-25`.
- **Frontend invariants:** `chatApi.ts:175-198` (idle-timeout `releaseLock()` leak prevention), `EditLlmRouteDialog.tsx:25-27` (`Number(x) || default` anti-pattern guard), `roles.ts:7-11` (backend-sync SOT), `summary.ts:4-15` (first-divider split rule), `apiClient.ts:1-13,71-73` (cookie auth + TS index-signature), `pagination.ts:1-5,18`.

---

## Suggested execution order

1. **Phase 1** first (dead code + stale fixes) — zero risk, immediate signal reduction.
2. **Phase 2** in file-grouped commits (backend app, backend tests, frontend src, frontend tests) — mechanical, run the relevant test suite after each group.
3. **Phase 3** last, one REFACTOR item per commit where it changes types/contracts (especially `lifecycle.py:31` `time`→`time_ms`, which is an API contract change — needs a coordinated frontend+backend change).

Each phase is independently shippable. Phase 1 + Phase 2 remove ~250 noise items with no behavior change; Phase 3 is ~15 small refactors that make the code represent itself.
