# Migrate Tortoise-ORM + Aerich → SQLAlchemy 2 + Alembic (with PGroonga)

- Status: Approved design, ready for implementation planning
- Date: 2026-08-19
- Scope: Backend data-access layer (`backend/`)

## 1. Goal & motivation

Replace the backend's data layer — **Tortoise-ORM 0.21 + Aerich** — with
**SQLAlchemy 2 (async) + Alembic**, and swap the Postgres image from
`pgvector/pgvector:pg16` to **`groonga/pgroonga:4.0.8-debian-17`**.

Drivers (user-selected): **ecosystem & long-term maintainability**, and a
**trustworthy migration story**. Not driven by a need for more raw-SQL power.

This is an architectural, cross-cutting change: 28 files import `tortoise`, 14
models, 31 Aerich migrations, ~60 test files.

## 2. Decisions (locked)

| Question | Decision |
|---|---|
| Test database | **Real Postgres via testcontainers** (`groonga/pgroonga:4.0.8-debian-17`) — highest fidelity, exercises PGroonga + analytics raw SQL. |
| Live data to preserve | **No — dev only, recreatable.** No Alembic stamping/adoption; fresh baseline. |
| Architectural scope | **Full repository layer.** ALL data access behind repository ports; services hold zero raw queries. |
| Session strategy | **Session injection (`get_db`).** A FastAPI dependency yields a request-scoped `AsyncSession` wrapped in `session.begin()` — the dependency owns one transaction per request (commit-on-success, rollback-on-exception). Repos are module functions taking `session` first. No UoW object. |
| Search engine | **PGroonga** replaces pg_trgm. pgvector is vestigial (embedding column dropped in migration 19) and is removed. |
| DB image | `groonga/pgroonga:4.0.8-debian-17` (compose, testcontainers, deploy). |
| Cutover | **Big-bang on a branch** (`refactor/sqlalchemy-migration`). Two ORMs cannot share the same tables; dev-only data means no dual-write phase. |

## 3. Model layer (Tortoise `Model` → SQLAlchemy 2 declarative)

All 14 models move to typed declarative mappings on a shared
`Base(DeclarativeBase)`. Table names and columns stay **schema-identical** to
today (no data, but we keep the shape for review sanity and analytics SQL).

- `UUIDField(primary_key=True, default=generate_uuid)` →
  `Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)`.
- `JSONField(default=list/dict)` → `mapped_column(JSONB, default=...)` with
  callable defaults. Where a service mutates JSON **in place** (e.g.
  `agency.api_endpoints`), wrap with `MutableList.as_mutable(JSONB)` /
  `MutableDict.as_mutable(JSONB)`.
- `CharEnumField(SomeEnum)` → keep the `str, Enum` classes; store as
  `String(n)` (varchar) matching Tortoise's current storage — **not** native
  PG `ENUM` — so the schema is identical. Enum coercion in the mapping.
- `auto_now_add` → `server_default=func.now()`; `auto_now` → `onupdate=func.now()`
  (or Python `default=now`), preserving created/updated semantics.
- Model-level `ordering` has no SQLAlchemy equivalent → moves into repository
  `.order_by(...)` clauses.
- `app/models/__init__.py` keeps exporting model classes so imports stay stable.
- No `Vector` type is needed (embedding column already dropped).

## 4. Session infrastructure (`get_db` dependency)

New `app/db.py` (replaces the Tortoise bootstrap in `database.py`):

- **Engine**: `create_async_engine("postgresql+asyncpg://…", pool_size=…, connect_args=…)`.
  URL normalization (`postgres://` → `postgresql+asyncpg://`) and the current
  `sslmode`→`ssl` handling move from `_build_tortoise_orm` into `database_url()`
  + `connect_args()`, keeping `test_database_config.py`'s parsing contract.
- **`AsyncSessionLocal = async_sessionmaker(expire_on_commit=False)`** — routers
  serialize ORM objects *after* the request transaction commits, so attributes
  must stay loaded.
- **FastAPI dependency `get_db()`** — the transaction boundary:
  ```python
  async def get_db() -> AsyncGenerator[AsyncSession, None]:
      async with AsyncSessionLocal() as session:
          async with session.begin():
              yield session
  ```
  One transaction per request: commit-on-success, rollback-on-exception.
  Services and routers **never call `commit()`**; `await session.flush()` when a
  PK is needed mid-transaction.
- **Non-request contexts** open a session the same way:
  `async with AsyncSessionLocal() as session, session.begin(): ...` — APScheduler
  jobs, the MCP server's `_fetch_agencies`, `seed_llm_defaults`, CLI scripts.
- **Streaming exception (ruling):** chat SSE/WS endpoints must NOT hold the
  request transaction open for the stream's lifetime (it would pin a DB
  connection). `turn.py`'s end-of-turn persistence opens its **own** short-lived
  `AsyncSessionLocal()` + `begin()`, not the request-scoped `get_db` session.

**Transactional outbox stays transactional.**
`events.publish(session, event_type, payload)` inserts the `DomainEvent` on the
same `session`. Because `turn.py`'s conversation + 2 messages + event share one
`session.begin()` block, they commit atomically — the exact semantics of today's
`in_transaction()`, without ambient magic.

## 5. Repository layer (full coverage)

- Repositories stay **module-level functions** under `app/repositories/`
  (matching today's style), now taking `session` as the first argument
  (`await agency_repo.by_id(session, agency_id)`), exposing intention-revealing
  functions (`by_id`, `list_and_count`, `create`, `save`, `delete`,
  `increment_calls`, `count_all`, …). Existing 3 repos' names are preserved to
  minimise caller churn; the only signature change is the leading `session`.
- **Raw-SQL / analytics services** (`similarity`, `public_status`,
  `analytics/{heatmap,brief,health,dashboard,usage}`, `feedback`) move their SQL
  behind **read-model repository** functions (e.g. `analytics_repo.heatmap(session, …)`,
  `similarity_repo.find_similar(session, …)`) that run `text()` / Core `select()`
  against `session`. Services stop importing `tortoise` entirely — **zero raw
  queries in services**.
- Translations: `F("total_calls") + 1` → `update(...).values(total_calls=Agency.total_calls + 1)`;
  `RawSQL(...)` annotations → `func.*` / `text()` in the read-model repos.

## 6. Search: pg_trgm → PGroonga

Only `similarity.py`'s "similar prior question" cache uses text search
(`similarity(content, $1)`, pg_trgm). Rewrite:

- **Extension**: baseline runs `CREATE EXTENSION IF NOT EXISTS pgroonga;`
  (replaces `pg_trgm`).
- **Index**: `CREATE INDEX ... ON messages USING pgroonga (content)` (replaces
  the trigram GIN index).
- **Query**: pg_trgm `similarity()` → PGroonga **similar-search** operator
  `&@*`, ordered by `pgroonga_score(tableoid, ctid) DESC LIMIT 1`, filtered to
  `role='user'` and `created_at >= cutoff`.
- **The old SQLite/Postgres fork collapses**: `_fetch_answer_by_match`'s
  positional-`?` SQLite branch is removed — tests now run on real Postgres, so
  only the `$1` Postgres path remains.

### Behavioral caveat + calibration knob

PGroonga scores are **not** the normalized 0–1 that pg_trgm's `similarity()`
returns, so `SIMILARITY_THRESHOLD` cannot carry its numeric meaning across
verbatim. The *feature* is preserved (one similar successful prior question,
above a floor). `SIMILARITY_THRESHOLD` is re-interpreted as a PGroonga-score
floor and **must be re-tuned**. The PGroonga tokenizer/normalizer (e.g.
`NormalizerNFKC150`) is left as a documented, tunable knob — Thai relevance
needs calibration the port cannot guess. This is the one *semantic* change in
the migration and gets its own test.

Assumptions (confirmed with user): keep the same similar-question **cache**
feature (not general full-text search); dropping pg_trgm entirely is fine.

## 7. Alembic

- **Layout**: `backend/alembic/` (`env.py`, `script.py.mako`, `versions/`),
  `alembic.ini` at `backend/`. `env.py` reads `DATABASE_URL` from
  `app.config.settings` (15-factor: no hardcoded URL) and imports `app.models`
  so `target_metadata = Base.metadata`.
- **Async env**: migrations run via `async_engine` +
  `connection.run_sync(context.run_migrations)` (standard async template).
- **Baseline (single squashed initial revision)**: dev-only + recreatable, so
  the 31 Aerich migrations collapse into ONE initial revision that:
  1. `CREATE EXTENSION IF NOT EXISTS pgroonga;`
  2. creates all 14 tables from `Base.metadata`;
  3. creates the PGroonga index on `messages.content`.
  Generated via `alembic revision --autogenerate`, then hand-verified;
  the extension and PGroonga index are added manually (autogenerate won't emit
  them).
- **No stamping** (no data). Fresh envs just `alembic upgrade head`.
- The entire `backend/migrations/` (Aerich) tree and `[tool.aerich]` are deleted.

## 8. Startup & config

- `database.py` → `db.py`:
  - `init_db()` → `await run_migrations()` (programmatic Alembic
    `command.upgrade(cfg, "head")`) then `await seed_llm_defaults(session)` inside
    `async with AsyncSessionLocal() as session, session.begin():`.
  - **Drop** `Tortoise.generate_schemas(safe=True)` — Alembic is the single
    source of schema truth (15-factor: explicit versioned migrations, not
    runtime schema generation).
  - `close_db()` → `await engine.dispose()`.
- `config.py`: replace `_build_tortoise_orm` / `TORTOISE_ORM` with
  `build_async_url()` + `connect_args`; pool sizing → `create_async_engine`
  kwargs. Keep URL parsing + `sslmode`→`ssl` so `test_database_config.py`
  passes (rewritten to assert the SQLAlchemy URL/connect_args).
- `pyproject.toml`: remove `tortoise-orm`, `aerich`, `pgvector`; add
  `sqlalchemy[asyncio]>=2.0`, `alembic>=1.13`, `asyncpg` (now a direct dep);
  dev adds `testcontainers[postgres]>=4`.

## 9. Test harness

- **Session-scoped Postgres container** (`testcontainers`, image
  `groonga/pgroonga:4.0.8-debian-17`). A fixture runs `alembic upgrade head`
  once against it — this also validates the baseline on every run.
- **Per-test isolation**: each test runs in a transaction rolled back at
  teardown (outer `connection.begin()` + `join_transaction_mode="create_savepoint"`).
  The `db_session` fixture yields an `AsyncSession` bound to that transaction, and
  overrides `get_db` to yield the same session. `conftest`'s SQLite `Tortoise.init`
  fixture is removed.
- **Payoff**: `similarity` (PGroonga `&@*`), `public_status`, and all
  `analytics/*` raw-SQL paths get **real coverage for the first time** — they
  were untestable on the old SQLite fixture.
- ~60 test files: most need only the fixture swap (`db_session` instead of the
  ambient Tortoise `db` fixture). Tortoise-specific assertions are ported
  case-by-case.

## 10. Risks

1. **PGroonga threshold recalibration** — the one semantic change; dedicated
   test + tuning knob (§6).
2. **`expire_on_commit=False`** correctness for post-commit serialization in
   routers.
3. **JSON in-place mutation** — `MutableList`/`MutableDict` where services
   mutate JSON fields (§3).
4. **Timestamp parity** — `auto_now`/`auto_now_add` vs `server_default`/`onupdate`.
5. **The ~60-test port is the bulk of the effort**, not the models.

## 11. Out of scope

- Any data migration (no live data).
- General full-text search beyond the existing similar-question cache.
- Frontend changes.
- Changing table shapes / normalizing the schema.

## 12. Method

- Branch `refactor/sqlalchemy-migration`; TDD per model/repo/service.
- On completion: update `CONTEXT.md`, commit, and validate via docker compose.
- Next step after this spec: the writing-plans skill produces the phased
  implementation plan.
