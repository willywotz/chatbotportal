# Design — Backend feature-based clean architecture (2026-09-23)

Written in Simplified Technical English.

## Goal

Reorganize `backend/app` from technical layers (`models/`, `repositories/`,
`services/`, `routers/`, `schemas/`, `auth/`) into **feature slices**. Each slice
owns its own delivery, use-case, data-access, and schema files. The dependency
rule points inward: a feature imports the shared kernel (`core/`), never another
feature's router or service.

Scope decision (approved 2026-09-23): **structural reorganization only.**
- Keep the current SQLAlchemy 2 + module-level repository (session-first) pattern.
- Keep the transactional outbox as-is; add no new events.
- Add no repository ports, no pure-entity rewrite, no unit-of-work.
- Behavior, routes, status codes, and JSON bodies stay **byte-identical**.

This is a move-and-rewire task, not a rewrite. The 8-slice map in
`docs/go-port-feature-slices-2026-08-18.md` defines the feature boundaries; this
spec applies it to the current SQLAlchemy tree.

## Non-goals

- No behavior change. No route rename. No schema/migration change.
- No new domain events, ports, or entity classes (that is the rejected Tier B).
- No change to `web/`, `deploy/`, `compose*.yaml`, or the OpenAPI contract.

## Target layout

```
backend/app/
  main.py                 composition root — mounts every feature router
  scheduler.py            composition root — registers every feature job
  core/                   shared kernel — imported by features, imports no feature
    config.py             <- app/config.py
    db.py                 <- app/db.py (engine, AsyncSessionLocal, get_db)
    base.py               <- app/models/base.py (Base + naming convention)
    errors.py             <- app/errors.py (ApiError, error envelope)
    concurrency.py        <- app/concurrency.py (spawn_logged)
    trace_util.py         <- app/trace_util.py (QueryTraceparentASGI)
    usage_context.py      <- app/services/usage_context.py
    log_sanitize.py       <- app/services/log_sanitize.py
    events.py             <- app/services/events.py + event_consumers.py (outbox)
    audit.py              <- app/services/audit.py (record_audit)
    connection_log.py     <- app/services/connection_log.py
    security/
      principal.py        <- app/auth/principal.py
      scopes.py           <- app/auth/scopes.py
      dependencies.py     <- app/auth/dependencies.py (require_scope)
      tokens.py           <- app/auth/oidc/tokens.py (verify_token + key cache)
    models/               shared-kernel tables: event.py, audit.py, connection_log.py
    repositories/         event.py, audit.py, connection_log.py
    utils/                <- app/utils/ (retry.py, uuid7.py, __init__: now, generate_uuid)
    registry.py           imports every feature model module → fills Base.metadata
  features/
    identity/    auth, users, api-keys, OIDC provider, signing keys
    settings/    settings key/value + cache flush
    llm/         LLM gateway, routing, rate limit, usage metering
    onechat/     OneChat transport adapter + session warm-up
    chat/        chat pipeline, conversation, message, similarity, DTOs
    agency/      CRUD, golden, lifecycle, health, conformance, evaluation, spec, seed
    mcp/         FastMCP server + agent-proxy
    analytics/   dashboard, insight, heatmap, brief, feedback, popular questions,
                 audit-log read, public status
```

Feature internal shape (uniform): `routers/`, `services/`, `repositories/`,
`schemas/`, `models/`. Small features may keep single files; large ones (chat,
agency, analytics, identity) use the subpackages.

## Shared-kernel rule

A module lands in `core/` when it has **no single feature owner** — it is
written or used by two or more features, or it is framework/infra glue:

- Infra glue: `config`, `db`, `base`, `errors`, `concurrency`, `trace_util`, `utils`.
- Cross-cutting request state: `usage_context`, `log_sanitize`.
- The security guard every protected route depends on: `security/*`
  (`principal`, `scopes`, `require_scope`, `verify_token` + public-key cache).
- Multi-writer tables and their write path: `DomainEvent`/`events` (outbox),
  `AuditLog`/`audit` (written by many features, read by analytics),
  `ConnectionLog`/`connection_log` (written by chat, mcp/agent-proxy, agency
  scheduler; read by analytics).

The OIDC **provider** (endpoints, key generation, password hashing) is the
identity feature. Only the token-verify guard + principal shape are kernel, so
`verify_token` stays I/O-free per request; identity fills the key cache at
startup exactly as today.

## Per-feature file mapping

### core (shared kernel)
| From | To |
|---|---|
| `app/config.py` | `core/config.py` |
| `app/db.py` | `core/db.py` |
| `app/models/base.py` | `core/base.py` |
| `app/errors.py` | `core/errors.py` |
| `app/concurrency.py` | `core/concurrency.py` |
| `app/trace_util.py` | `core/trace_util.py` |
| `app/utils/*` | `core/utils/*` |
| `app/services/usage_context.py` | `core/usage_context.py` |
| `app/services/log_sanitize.py` | `core/log_sanitize.py` |
| `app/services/events.py`, `event_consumers.py` | `core/events.py` |
| `app/services/audit.py` | `core/audit.py` |
| `app/services/connection_log.py` | `core/connection_log.py` |
| `app/models/event.py`, `audit.py`, `connection_log.py` | `core/models/*` |
| `app/repositories/event.py`, `audit.py`, `connection_log.py` | `core/repositories/*` |
| `app/auth/principal.py`, `scopes.py`, `dependencies.py` | `core/security/*` |
| `app/auth/oidc/tokens.py` | `core/security/tokens.py` |

### identity
| From | To |
|---|---|
| `routers/auth.py`, `routers/users.py` | `features/identity/routers/*` |
| `services/user_admin.py`, `user_seed.py` | `features/identity/services/*` |
| `repositories/user.py`, `oauth.py`, `signing_key.py` | `features/identity/repositories/*` |
| `models/user.py`, `oauth.py`, `signing_key.py` | `features/identity/models/*` |
| `schemas/user.py` | `features/identity/schemas/user.py` |
| `app/auth/oidc/{provider,router,keys,passwords}.py` | `features/identity/oidc/*` |

### settings
| From | To |
|---|---|
| `routers/settings.py` | `features/settings/routers/settings.py` |
| `services/settings.py`, `cache_flush.py` | `features/settings/services/*` |
| `models/setting.py` | `features/settings/models/setting.py` |
| `repositories/setting.py` | `features/settings/repositories/setting.py` |
| `schemas/settings.py` | `features/settings/schemas/settings.py` |

### llm
| From | To |
|---|---|
| `routers/llm.py` | `features/llm/routers/llm.py` |
| `services/llm/{client,admin,purpose,seed,usage}.py` | `features/llm/services/*` |
| `services/rate_limit.py` | `features/llm/services/rate_limit.py` |
| `models/{llm_provider,llm_route,llm_usage,rate_limit_counter}.py` | `features/llm/models/*` |
| `repositories/{llm,llm_usage,rate_limit}.py` | `features/llm/repositories/*` |
| `schemas/{llm_provider,llm_route}.py` | `features/llm/schemas/*` |

### onechat
| From | To |
|---|---|
| `services/onechat/client.py`, `__init__.py` | `features/onechat/services/*` |
| `services/session.py` | `features/onechat/services/session.py` |

### chat
| From | To |
|---|---|
| `routers/{chat,conversations,messages}.py` | `features/chat/routers/*` |
| `services/chat/{stream,turn,llm,model,pipeline_snapshot,dispatch,aggregate}.py` | `features/chat/services/*` |
| `services/{conversation,message,similarity}.py` | `features/chat/services/*` |
| `models/conversation.py` (Conversation, Message) | `features/chat/models/conversation.py` |
| `repositories/{conversation,message,similarity}.py` | `features/chat/repositories/*` |
| `schemas/{chat,conversation,responses,openai_conversations}.py` | `features/chat/schemas/*` |

### agency
| From | To |
|---|---|
| `routers/agencies/*` | `features/agency/routers/*` |
| `services/{agency,agency_golden,agency_health,agency_lifecycle,agency_reconcile,conformance,evaluation,mcp_discovery,seed}.py` | `features/agency/services/*` |
| `models/{agency,evaluation}.py` | `features/agency/models/*` |
| `repositories/{agency,evaluation}.py` | `features/agency/repositories/*` |
| `schemas/agency.py` | `features/agency/schemas/agency.py` |

`services/seed.py` holds `run_seed_agencies` → agency feature.

### mcp
| From | To |
|---|---|
| `app/mcp/server.py` | `features/mcp/server.py` |
| `routers/agent_proxy.py` | `features/mcp/routers/agent_proxy.py` |
| `services/agent_proxy.py` | `features/mcp/services/agent_proxy.py` |

### analytics
| From | To |
|---|---|
| `routers/{dashboard,insight,executive_summary,feedback,connection_logs,popular_questions,audit_log,public_status}.py` | `features/analytics/routers/*` |
| `services/analytics/{dashboard,health,heatmap,brief,usage}.py` | `features/analytics/services/*` |
| `services/{feedback,popular_questions,public_status}.py` | `features/analytics/services/*` |
| `models/{executive_brief,popular_question}.py` | `features/analytics/models/*` |
| `repositories/{analytics,executive_brief,feedback_read,popular_question,public_status_read}.py` | `features/analytics/repositories/*` |
| `schemas/{executive_summary,insight,popular_question}.py` | `features/analytics/schemas/*` |

`audit_log` router reads through `core/audit`; `connection_logs` router reads
through `core/connection_log`. Analytics does not own those tables.

## Model registry & Alembic

- `Base` moves to `core/base.py`. Every model imports `from app.core.base import Base`.
- New `core/registry.py` imports each feature's model module (and core models),
  the same job the old `app/models/__init__.py` did.
- `alembic/env.py`: change `import app.models` → `import app.core.registry`.
  `target_metadata = Base.metadata` is unchanged.
- Cross-feature FKs stay as string relationships; the registry import order fills
  `Base.metadata` before any query, so mapper configuration still resolves.
- No migration is generated. After the move, `alembic revision --autogenerate`
  must report **no diff** — this is a regression gate.

## Import rewrite

- No compatibility shims. All imports across `app/` and `tests/` are rewritten to
  the new paths, so there is one source of truth.
- Method: move files with `git mv` (history kept), then rewrite `from app.<old>`
  → `from app.<new>` module by module. Rewrites are verified by import, not by
  eye: `python -c "import app.main"` and the test suite.
- `main.py` keeps importing feature routers and mounting them with the same
  `/api/v1` prefix and same include order → same route table.
- `scheduler.py` keeps importing the same job functions from their new homes.

## Execution plan (TDD + parity)

Order = dependency order, so each slice compiles before the next moves:

1. `core/` (kernel: config, db, base, errors, infra, security, events, audit,
   connection_log, registry). Wire `alembic/env.py` to `core/registry`.
2. identity → 3. settings → 4. llm → 5. onechat → 6. chat → 7. agency →
   8. mcp → 9. analytics.

Per slice (Red→Green→Refactor, adapted to a move):
- **Red/guard:** run the slice's existing tests; they are green now and define
  the parity contract. Move the test files to `tests/features/<slice>/` first.
- **Green:** `git mv` the source files, rewrite imports, until `import app.main`
  succeeds and the slice's tests pass again.
- **Refactor:** run the full backend suite. It must stay green.
- Commit the slice. Then `alembic revision --autogenerate` shows no diff on the
  final slice.

Regression gates (all must pass before the branch is done):
- Full backend test suite green (87 test files).
- `tests/test_route_audit.py` and any surface-parity test green (route table +
  scopes unchanged).
- `alembic upgrade head` clean and autogenerate reports no diff.
- `import app.main` and `uvicorn` boot with no ImportError.

## Risks & mitigations

- **Circular imports** when a former flat module now sits under a feature that
  another feature imports. Mitigation: the shared-kernel rule pulls every
  multi-consumer module into `core/`; features never import feature routers.
- **Mapper resolution / FK order.** Mitigation: `core/registry.py` imports all
  model modules; alembic and startup import it first.
- **Hidden importers outside `backend/app`** (scripts, `alembic/versions`,
  `scheduler`, MCP mount). Mitigation: grep the whole `backend/` tree for
  `app.services`/`app.routers`/`app.models`/`app.auth` before declaring a slice
  done.
- **`__init__.py` re-exports** relied on by tests. Mitigation: rewrite the test
  imports too; no shims left behind.
- Scope creep into Tier B. Mitigation: this spec forbids ports/entities/new
  events; a reviewer rejects any such change.

## Definition of done

- New tree in place; `app/models`, `app/repositories`, `app/routers`,
  `app/schemas`, `app/services`, `app/auth` folders removed.
- All regression gates green.
- `MEMORY.md` updated (layout + import conventions); this spec committed.
