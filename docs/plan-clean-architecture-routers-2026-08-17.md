# Plan — Clean Architecture across all routers (2026-08-17)

Goal: no router builds ORM queries. Every router calls a service. The service owns
the data model. Written in Simplified Technical English.

## Rule for every batch
- Move each `Model.filter/get/create/save/all/exclude/count/delete/...` call out of the
  router and into the matching service module under `app/services/`.
- The router keeps only orchestration: parse input, call the service, record audit, map to
  a schema, return.
- The router may still import a model **only** for a type hint (for example
  `admin: User = Depends(require_admin)`). It must build no queryset.
- TDD: write or extend a service test first (red), implement (green), then thin the router.
- Keep behavior identical. Do not change routes, status codes, or response shapes.

## Batches (file-disjoint, safe to run in parallel worktrees)

| # | Routers (ORM calls) | Service target |
|---|---------------------|----------------|
| 1 | agencies/crud (7), agencies/golden (6), agencies/lifecycle (5), agencies/logo (1) | app/services/agency*.py |
| 2 | llm (15) | app/services/llm/* |
| 3 | conversations (8), messages (2) | app/services/chat/* or new conversation service |
| 4 | openai_conversations (7) | app/services/openai/* |
| 5 | feedback (9), insight (6), popular_questions (6) | app/services/analytics/*, popular_questions.py |
| 6 | api_key (5), settings (1), auth (3) | app/services/api_key, settings, auth_session |
| 7 | connection_logs (4), audit_log (1), public_status (2) | app/services/audit.py + new services |

Already clean (0 ORM calls): users (done), agencies/spec, agencies/_utils, chat, dashboard,
executive_summary, responses.

Deferred to the 15-Factor pass: `seed.py` (5) — it becomes a CLI/management command
(Factor XII), so refactoring its ORM into a service now is wasted work.

## Execution
1. Seven builder workers, each isolated in its own git worktree (safe: every router test
   imports the whole app, so a shared tree is not safe for parallel edits).
2. Each worker runs its own batch tests inside its worktree and returns a patch.
3. The orchestrator (main) applies all patches to the main tree, runs the **full** backend
   suite once, and commits per batch. Main owns git and CONTEXT.md.
4. If the full suite fails, the orchestrator fixes before commit.

## Out of scope (this pass)
- 15-Factor uploads-to-object-storage and seed-to-CLI. Deferred by user choice.
- Event-driven audit outbox. Deferred by user choice.
