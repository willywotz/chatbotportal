# Tortoise → SQLAlchemy 2 + Alembic Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the backend's Tortoise-ORM + Aerich data layer with SQLAlchemy 2 (async) + Alembic behind a full repository layer, using a request-scoped `get_db` session dependency, and swap the Postgres image to PGroonga.

**Architecture:** A FastAPI `get_db()` dependency yields a request-scoped `AsyncSession` wrapped in `session.begin()` — the dependency owns one transaction per request (commit-on-success, rollback-on-exception). All data access is via module-level repository functions taking `session` first; services take `session` and never call `commit()`. Alembic (single squashed baseline) is the sole schema source of truth. Text search moves from pg_trgm to PGroonga. Tests run against a real Postgres testcontainer.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, PostgreSQL 17 + PGroonga, pytest + testcontainers.

**Spec:** `docs/superpowers/specs/2026-08-19-tortoise-to-sqlalchemy-migration-design.md`

## Global Constraints

- SQLAlchemy `>=2.0` (async), Alembic `>=1.13`, `asyncpg` direct dep, `testcontainers[postgres]>=4` (dev). Remove `tortoise-orm`, `aerich`, `pgvector`.
- Postgres image (compose, deploy, testcontainers): `groonga/pgroonga:4.0.8-debian-17` — exact tag, verbatim.
- Engine URL scheme: `postgresql+asyncpg://`. Keep `sslmode`→`ssl` mapping.
- `AsyncSessionLocal = async_sessionmaker(expire_on_commit=False)`. The `get_db()` dependency owns the transaction via `async with session.begin()`. Services/routers NEVER call `commit()`; use `await session.flush()` for mid-transaction PKs.
- Schema source-of-truth is Alembic ONLY — no `generate_schemas`/`create_all` at runtime.
- Tables stay schema-identical to today: enums stored as **varchar** via `mapped_column(Enum(EnumClass, native_enum=False, create_constraint=False, length=n), default=EnumClass.member)` — NOT plain `String` (reads must coerce back to the enum; the app calls `.status.value` / `.connection_type.value`) and NOT native PG ENUM. Keep the original explicit `length` (e.g. connection_type=10, status=20). Same table/column names; FK `ondelete` preserved (CASCADE / RESTRICT / SET NULL as inventoried).
- Repositories are **module-level functions taking `session` first** (matching today's style). Services import zero `tortoise` and hold zero raw queries — all data access via repository functions.
- Chat streaming persistence (`turn.py`) opens its OWN short-lived `AsyncSessionLocal()`+`begin()`, NOT the request-scoped `get_db` session (avoids pinning a connection for the stream's lifetime).
- Branch: `refactor/sqlalchemy-migration` (already created). TDD per task, frequent commits. American English naming; full words for any new public route.

---

## Model inventory (15 classes → tables)

| Class | Table | PK | FKs (ondelete) | Enums | Notes |
|---|---|---|---|---|---|
| Agency | agencies | id UUID | — | ConnectionType, AgencyStatus (varchar) | order by name |
| AuditLog | audit_logs | id UUID | — | — | order -created_at |
| ConnectionLog | connection_logs | id UUID | agency_id→agencies (CASCADE, null) | — | order -created_at |
| Conversation | conversations | id UUID | — | — | Thai default title, order -created_at |
| Message | messages | id UUID | conversation_id→conversations (CASCADE) | — | PGroonga index on content; order created_at |
| GoldenQuestion | golden_questions | id UUID | agency_id→agencies (CASCADE) | — | |
| EvalResult | eval_results | id UUID | golden_question_id→golden_questions (CASCADE) | — | order -created_at |
| DomainEvent | domain_events | id UUID | — | — | outbox; order created_at |
| ExecutiveBrief | executive_briefs | id UUID | — | — | order -generated_at |
| LlmProvider | llm_providers | id UUID | — | — | name unique |
| LlmRoute | llm_routes | id UUID | provider_id→llm_providers (RESTRICT) | — | purpose unique |
| LlmUsage | llm_usage | id UUID | — | — | order -created_at; total_tokens property |
| PopularQuestion | popular_questions | id UUID | agency_id→agencies (SET NULL, null) | PopularQuestionSource (varchar) | text_key unique; order -pinned,sort_order,-created_at |
| RateLimitCounter | rate_limit_counters | id BigInt autoincrement | — | — | unique(key, window_start) |
| Setting | settings | key varchar (PK) | — | — | no id column |

## Tortoise → SQLAlchemy 2 idiom table (apply everywhere)

`session` is the `AsyncSession` (request-scoped from `get_db`, or opened directly in non-request contexts).

| Tortoise | SQLAlchemy 2 (async) |
|---|---|
| `Model.get_or_none(id=x)` | `await session.get(Model, x)` (PK) or `(await session.execute(select(Model).filter_by(**f))).scalar_one_or_none()` |
| `Model.get(id=x)` (raises) | `await session.get(Model, x)` then `if row is None: raise` |
| `Model.all()` | `select(Model)` |
| `qs.filter(a=b)` | `.where(Model.a == b)` |
| `qs.filter(name__icontains=s)` | `.where(Model.name.ilike(f"%{s}%"))` |
| `qs.filter(created_at__gte=d)` / `__lt` | `.where(Model.created_at >= d)` / `< d` |
| `qs.filter(field__isnull=False)` | `.where(Model.field.is_not(None))` |
| `qs.filter(json_col__contains=v)` | `.where(Model.json_col.contains(v))` (JSONB `@>`; `from sqlalchemy.dialects.postgresql import JSONB`) |
| `qs.exclude(status="draft")` | `.where(Model.status != "draft")` |
| `qs.order_by("-created_at")` | `.order_by(Model.created_at.desc())` |
| `qs.offset(o).limit(n)` | `.offset(o).limit(n)` |
| `await qs` (list) | `(await session.execute(stmt)).scalars().all()` |
| `await qs.count()` | `(await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()` |
| `await qs.first()` | `(await session.execute(stmt.limit(1))).scalars().first()` |
| `await qs.exists()` | `(await session.execute(select(literal(True)).where(...).limit(1))).scalar() is not None` |
| `Model.create(**f)` | `obj = Model(**f); session.add(obj); await session.flush(); return obj` |
| `obj.save(update_fields=...)` | dirty attrs flush on the request-transaction commit; call `await session.flush()` if an id/refresh is needed now |
| `obj.delete()` | `await session.delete(obj)` |
| `Model.filter(id=x).update(col=F("col")+1)` | `await session.execute(update(Model).where(Model.id==x).values(col=Model.col+1))` |
| `obj.refresh_from_db(fields=[...])` | `await session.refresh(obj, attribute_names=[...])` |
| `Model.bulk_create(rows, ignore_conflicts=True)` | `stmt = pg_insert(Model).values([...]).on_conflict_do_nothing(); await session.execute(stmt)` (`from sqlalchemy.dialects.postgresql import insert as pg_insert`) |
| `obj.update_from_dict(d).save()` | `for k,v in d.items(): setattr(obj,k,v)` then flush on commit |
| `.prefetch_related("agency")` | `.options(selectinload(Model.agency))` |
| `in_transaction()` | the `get_db` dependency already owns one transaction; use `session`. For raw: `await session.execute(text("SET LOCAL TIME ZONE :tz"), {"tz": settings.TIMEZONE})` |
| `conn.execute_query_dict(sql, params)` | `(await session.execute(text(sql), params_dict)).mappings().all()` — convert `$1` to `:name` bind params |
| `RawSQL("expr")` annotation | `func.*` / `text("expr")` inside the read-model repo's `select` |
| `Tortoise.get_connection("default")` | the `session` |

> Raw SQL note: replace asyncpg positional `$1` with SQLAlchemy named binds (`:query`, `:cutoff`, …). Use `SET LOCAL TIME ZONE` inside the request transaction so the timezone never leaks to the next pooled checkout.

---

# Phase 0 — Dependencies & image swap

### Task 0: Swap dependencies and Postgres image

**Files:**
- Modify: `backend/pyproject.toml` (deps + remove `[tool.aerich]`)
- Modify: `compose.yaml:4` (postgres image)
- Modify: `deploy/` postgres image references (grep first)

- [ ] **Step 1: Edit `pyproject.toml` dependencies**

Remove `"tortoise-orm[asyncpg]>=0.21.0"`, `"pgvector>=0.3.0"`, `"aerich>=0.7.2"`. Add:
```toml
    "sqlalchemy[asyncio]>=2.0.0",
    "alembic>=1.13.0",
    "asyncpg>=0.29.0",
```
In `[project.optional-dependencies].dev` add:
```toml
    "testcontainers[postgres]>=4.0.0",
```
Delete the entire `[tool.aerich]` block.

- [ ] **Step 2: Swap the compose image**

In `compose.yaml:4` change `image: pgvector/pgvector:pg16` → `image: groonga/pgroonga:4.0.8-debian-17`.

- [ ] **Step 3: Swap deploy references**

Run: `grep -rn "pgvector/pgvector" deploy/ compose.override.yaml`
Replace every match with `groonga/pgroonga:4.0.8-debian-17`.

- [ ] **Step 4: Sync the environment**

Run: `cd backend && uv sync --extra dev`
Expected: resolves with sqlalchemy/alembic/asyncpg/testcontainers installed, no tortoise/aerich.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml compose.yaml deploy/ compose.override.yaml
git commit -m "build: swap tortoise/aerich/pgvector for sqlalchemy/alembic + pgroonga image"
```

---

# Phase 1 — Declarative Base, config, engine + get_db

### Task 1: Declarative `Base` and naming convention

**Files:**
- Create: `backend/app/models/base.py`
- Test: `backend/tests/test_orm_base.py`

**Interfaces:**
- Produces: `Base` (DeclarativeBase) with a deterministic naming convention (clean Alembic diffs). Consumed by every model.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orm_base.py
from app.models.base import Base

def test_base_has_metadata_and_naming_convention():
    assert Base.metadata is not None
    assert "ix" in Base.metadata.naming_convention
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_orm_base.py -v`
Expected: FAIL (`ModuleNotFoundError: app.models.base`).

- [ ] **Step 3: Implement**

```python
# app/models/base.py
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

_NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_orm_base.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/base.py backend/tests/test_orm_base.py
git commit -m "feat(db): SQLAlchemy declarative Base with naming convention"
```

### Task 2: Config — async URL + connect args (replaces `_build_tortoise_orm`)

**Files:**
- Modify: `backend/app/config.py:193-238` (replace `_build_tortoise_orm` / `TORTOISE_ORM`)
- Test: `backend/tests/test_database_config.py` (rewrite)

**Interfaces:**
- Produces: `database_url(s: Settings) -> str` (a `postgresql+asyncpg://` URL, no query string) and `connect_args(s: Settings) -> dict`. `TORTOISE_ORM` is deleted.

- [ ] **Step 1: Rewrite the failing test**

```python
# tests/test_database_config.py
from app.config import Settings, database_url, connect_args


def test_plain_url_becomes_asyncpg_scheme():
    s = Settings(DATABASE_URL="postgres://alice:secret@db.example.com:5433/mydb")
    assert database_url(s) == "postgresql+asyncpg://alice:secret@db.example.com:5433/mydb"
    assert connect_args(s) == {}


def test_sslmode_require_maps_to_ssl_connect_arg():
    s = Settings(DATABASE_URL="postgres://u:p@host:5432/db?sslmode=require")
    assert "sslmode" not in database_url(s)
    assert connect_args(s)["ssl"] == "require"


def test_sslmode_verify_full_maps_to_ssl():
    s = Settings(DATABASE_URL="postgres://u:p@host:5432/db?sslmode=verify-full")
    assert connect_args(s)["ssl"] == "verify-full"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_database_config.py -v`
Expected: FAIL (`ImportError: database_url`).

- [ ] **Step 3: Implement in `config.py`**

Replace `_build_tortoise_orm` and the `TORTOISE_ORM = ...` line with:
```python
from urllib.parse import parse_qs, urlparse, urlunparse


def database_url(s: "Settings") -> str:
    parsed = urlparse(s.DATABASE_URL)
    if not parsed.hostname:
        raise ValueError(f"DATABASE_URL is malformed: {s.DATABASE_URL!r}")
    return urlunparse(("postgresql+asyncpg", parsed.netloc, parsed.path, "", "", ""))


def connect_args(s: "Settings") -> dict:
    parsed = urlparse(s.DATABASE_URL)
    query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    args: dict = {}
    sslmode = query.get("sslmode")
    if sslmode:
        # withinlazy: pass libpq-style string through; asyncpg accepts
        # "require"/"prefer"/"verify-full". Upgrade to an ssl.SSLContext if
        # client-cert verification is ever required.
        args["ssl"] = sslmode
    return args
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_database_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_database_config.py
git commit -m "feat(db): async DB URL + connect_args, drop TORTOISE_ORM"
```

### Task 3: Engine, `AsyncSessionLocal`, and `get_db` dependency

**Files:**
- Create: `backend/app/db.py`
- Test: `backend/tests/test_engine.py`

**Interfaces:**
- Produces: `engine` (`AsyncEngine`), `AsyncSessionLocal` (`async_sessionmaker[AsyncSession]`), `get_db()` (async generator FastAPI dependency that owns the request transaction), `close_db()`. Consumed by routers, services, startup (Task 30), and the test harness (Task 10). `run_migrations()`/`init_db()` land in Task 30.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine.py
from sqlalchemy.ext.asyncio import AsyncEngine
from app.db import engine, AsyncSessionLocal, get_db


def test_engine_uses_asyncpg_and_no_expire_on_commit():
    assert isinstance(engine, AsyncEngine)
    assert engine.url.drivername == "postgresql+asyncpg"
    assert AsyncSessionLocal.kw["expire_on_commit"] is False


def test_get_db_is_async_generator_callable():
    import inspect
    assert inspect.isasyncgenfunction(get_db)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_engine.py -v`
Expected: FAIL (`ModuleNotFoundError: app.db`).

- [ ] **Step 3: Implement `app/db.py`**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)

from app.config import connect_args, database_url, settings

engine = create_async_engine(
    database_url(settings),
    connect_args=connect_args(settings),
    pool_size=settings.DB_POOL_MAX,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped session; the dependency owns one transaction.

    Commit-on-success, rollback-on-exception. Callers never commit.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session


async def close_db() -> None:
    await engine.dispose()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_engine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db.py backend/tests/test_engine.py
git commit -m "feat(db): async engine, sessionmaker, get_db transaction dependency"
```

---

# Phase 2 — Models

> Reference task 4 shows the full mapping shape for one model. Tasks 5–7 apply the identical pattern to the remaining models using the per-model deltas from the inventory table. Each model task ends by importing the class in `app/models/__init__.py` and running the metadata smoke test.

### Task 4: `Agency` model (reference mapping)

**Files:**
- Modify: `backend/app/models/agency.py` (rewrite mapping; keep the `ConnectionType`/`AgencyStatus` enums)
- Test: `backend/tests/test_orm_models.py` (create; grows across Phase 2)

**Interfaces:**
- Produces: `Agency` declarative model with all columns from the inventory, table `agencies`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orm_models.py
from app.models.base import Base
from app.models.agency import Agency, ConnectionType, AgencyStatus


def test_agency_table_and_columns():
    t = Agency.__table__
    assert t.name == "agencies"
    assert t.c.id.primary_key
    assert t.c.connection_type.default.arg == ConnectionType.API
    assert t.c.status.default.arg == AgencyStatus.active
    assert "agencies" in Base.metadata.tables
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_orm_models.py -v`
Expected: FAIL (import/attribute error).

- [ ] **Step 3: Rewrite `app/models/agency.py`**

```python
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils import generate_uuid


class ConnectionType(str, Enum):
    MCP = "MCP"; API = "API"; A2A = "A2A"


class AgencyStatus(str, Enum):
    draft = "draft"; active = "active"; maintenance = "maintenance"; disabled = "disabled"


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255))
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    logo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection_type: Mapped[ConnectionType] = mapped_column(String(10), default=ConnectionType.API)
    status: Mapped[AgencyStatus] = mapped_column(String(20), default=AgencyStatus.active)
    auto_maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    stats_reset_at: Mapped[datetime | None] = mapped_column(nullable=True)
    data_scope: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    endpoint_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    auth_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    auth_header: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    api_endpoints: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)
    response_schema: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)
    api_spec_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    api_headers: Mapped[list | None] = mapped_column(MutableList.as_mutable(JSONB), nullable=True, default=list)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    router_hint: Mapped[str] = mapped_column(Text, default="")
    dispatch_timeout_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mcp_tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conformance_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    rating_up: Mapped[int] = mapped_column(Integer, default=0)
    rating_down: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

Notes carried to every model: enum columns use `mapped_column(Enum(EnumClass, native_enum=False, create_constraint=False, length=n), default=EnumClass.member)` (varchar storage, reads coerce back to the enum — the app relies on `.value`); `auto_now_add`→`server_default=func.now()`; `auto_now`→ add `onupdate=func.now()`; JSON columns that services mutate in place use `MutableList/MutableDict.as_mutable(JSONB)`. For Agency, `connection_type` uses `length=10`, `status` uses `length=20`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_orm_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/agency.py backend/tests/test_orm_models.py
git commit -m "feat(models): map Agency to SQLAlchemy 2 declarative"
```

### Task 5: Independent models (no FK): AuditLog, DomainEvent, ExecutiveBrief, LlmProvider, LlmUsage, Setting, RateLimitCounter

**Files:**
- Modify: `app/models/{audit,event,executive_brief,llm_provider,llm_usage,setting,rate_limit_counter}.py`
- Test: extend `tests/test_orm_models.py`

Apply the Task-4 pattern per the inventory. Per-model deltas:
- **AuditLog** (`audit_logs`): `actor_id` UUID null, `detail` JSONB null, `created_at` server_default.
- **DomainEvent** (`domain_events`): `event_type` String(100), `payload` `MutableDict.as_mutable(JSONB)` default dict, `dispatched_at` datetime null.
- **ExecutiveBrief** (`executive_briefs`): `content` Text default "", `status` String(16) default "ok", `generated_at` server_default.
- **LlmProvider** (`llm_providers`): `name` String(50) `unique=True`; float `timeout_seconds` default 60.0; `created_at`/`updated_at`.
- **LlmUsage** (`llm_usage`): all UUID FKs are plain `UUID` columns (no relationship). Keep `total_tokens` as a Python `@property` returning `prompt_tokens + completion_tokens`.
- **Setting** (`settings`): PK is `key: Mapped[str] = mapped_column(String(100), primary_key=True)` — no `id`. `updated_at` `onupdate=func.now()`.
- **RateLimitCounter** (`rate_limit_counters`): `id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)`; add `__table_args__ = (UniqueConstraint("key", "window_start"),)`.

- [ ] **Step 1:** For each model add a `test_<model>_table_and_columns` asserting table name, PK, and one distinctive column/constraint.
- [ ] **Step 2:** Run `pytest tests/test_orm_models.py -v` — expect FAIL for the new asserts.
- [ ] **Step 3:** Rewrite each model file with the Task-4 pattern + deltas above.
- [ ] **Step 4:** Run `pytest tests/test_orm_models.py -v` — expect PASS.
- [ ] **Step 5:** Commit `feat(models): map independent models to SQLAlchemy 2`.

### Task 6: FK models: ConnectionLog, Conversation+Message, GoldenQuestion+EvalResult, LlmRoute, PopularQuestion

**Files:**
- Modify: `app/models/{connection_log,conversation,evaluation,llm_route,popular_question}.py`
- Test: extend `tests/test_orm_models.py`

FK pattern (example for ConnectionLog → Agency, CASCADE, nullable):
```python
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

agency_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=True,
)
agency: Mapped["Agency | None"] = relationship(lazy="raise")
```
Per-model FK deltas (ondelete verbatim from inventory):
- **ConnectionLog** (`connection_logs`): `agency_id`→agencies **CASCADE**, nullable. Plain UUID cols `message_id`, `assistant_message_id`. `action` default "test".
- **Conversation** (`conversations`): no FK; `title` String(500) default `"สนทนาใหม่"`; the Tortoise `metadata` field → **map Python attribute `meta` to DB column `metadata`** via `mapped_column("metadata", JSONB, default=dict)` (SQLAlchemy reserves `Base.metadata`; keep the DB column name, rename the attribute, and update the ~2 call sites that read `conv.metadata`). `agencies` JSONB default list; `response_time` String(50) null.
- **Message** (`messages`): `conversation_id`→conversations **CASCADE** (not null); plain UUID `parent_id`, `user_id`; JSONB list fields (`agent_steps`, `sources`, `summary_references`, `agency_ids`, `errors`).
- **GoldenQuestion** (`golden_questions`): `agency_id`→agencies **CASCADE**.
- **EvalResult** (`eval_results`): `golden_question_id`→golden_questions **CASCADE**; `score` Float.
- **LlmRoute** (`llm_routes`): `provider_id`→llm_providers **RESTRICT**; `purpose` String(50) unique.
- **PopularQuestion** (`popular_questions`): `agency_id`→agencies **SET NULL**, nullable; `text_key` unique; `source` uses `Enum(PopularQuestionSource, native_enum=False, create_constraint=False, length=10)` default manual.

- [ ] **Step 1:** Add per-model tests asserting the FK column, its `ondelete`, and the relationship exists. Example:
```python
def test_connection_log_fk_cascade():
    fk = list(ConnectionLog.__table__.c.agency_id.foreign_keys)[0]
    assert fk.column.table.name == "agencies"
    assert fk.ondelete == "CASCADE"
```
- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3:** Rewrite each model with FK pattern + deltas.
- [ ] **Step 4:** Run — expect PASS.
- [ ] **Step 5:** Commit `feat(models): map FK models with relationships`.

### Task 7: Wire `app/models/__init__.py` and metadata completeness test

**Files:**
- Modify: `backend/app/models/__init__.py`
- Test: extend `tests/test_orm_models.py`

- [ ] **Step 1: Write the failing test**

```python
def test_all_15_tables_registered():
    from app import models  # noqa: F401
    from app.models.base import Base
    expected = {
        "agencies", "audit_logs", "connection_logs", "conversations", "messages",
        "golden_questions", "eval_results", "domain_events", "executive_briefs",
        "llm_providers", "llm_routes", "llm_usage", "popular_questions",
        "rate_limit_counters", "settings",
    }
    assert expected <= set(Base.metadata.tables)
```

- [ ] **Step 2:** Run — expect FAIL if any model unimported.
- [ ] **Step 3:** Replace the star-imports in `__init__.py` with explicit class imports (keep the same exported names) so every model registers on `Base.metadata`.
- [ ] **Step 4:** Run — expect PASS.
- [ ] **Step 5:** Commit `feat(models): register all tables on Base.metadata`.

---

# Phase 3 — Alembic baseline

### Task 8: Alembic scaffolding (async env)

**Files:**
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/.gitkeep`

- [ ] **Step 1:** `cd backend && alembic init -t async alembic` then trim generated boilerplate.
- [ ] **Step 2:** Edit `alembic/env.py` to source the URL from settings and target our metadata:
```python
from app.config import connect_args, database_url, settings
from app.models.base import Base
import app.models  # noqa: F401  register all tables

config.set_main_option("sqlalchemy.url", database_url(settings))
target_metadata = Base.metadata
```
Keep the async `run_migrations_online` using `connection.run_sync(...)`; pass `connect_args(settings)` when it builds the engine.
- [ ] **Step 3:** `alembic.ini` — remove the hardcoded `sqlalchemy.url` line (env.py sets it; 15-factor).
- [ ] **Step 4:** Run `cd backend && alembic history` — expect no error, empty history.
- [ ] **Step 5:** Commit `chore(alembic): async migration scaffolding`.

### Task 9: Squashed initial baseline (extension + tables + PGroonga index)

**Files:**
- Create: `backend/alembic/versions/0001_initial.py`

- [ ] **Step 1:** With a throwaway Postgres up (`docker compose up -d postgres`), run:
`cd backend && alembic revision --autogenerate -m "initial"`
- [ ] **Step 2:** Hand-edit the generated revision:
  - At the top of `upgrade()`: `op.execute("CREATE EXTENSION IF NOT EXISTS pgroonga")`.
  - After table creation: `op.execute("CREATE INDEX ix_messages_content_pgroonga ON messages USING pgroonga (content)")`.
  - In `downgrade()`: drop the index, then `DROP EXTENSION IF EXISTS pgroonga`.
  - Verify all 15 tables + FKs (with ondelete) are present.
- [ ] **Step 3:** Verify against a clean DB:
`docker compose down -v && docker compose up -d postgres && cd backend && alembic upgrade head`
Expected: all tables created, PGroonga extension + index present (`\d messages`).
- [ ] **Step 4:** Sanity: `alembic downgrade base && alembic upgrade head` round-trips cleanly.
- [ ] **Step 5:** Commit `feat(alembic): squashed initial baseline with pgroonga`.

---

# Phase 4 — Test harness (real Postgres)

### Task 10: testcontainers fixture running Alembic

**Files:**
- Modify: `backend/tests/conftest.py` (replace the SQLite `db` fixture)
- Test: `backend/tests/test_harness_smoke.py`

**Interfaces:**
- Produces: session-scoped `pg_container` (PGroonga image) + `_engine` (Alembic-upgraded); a function-scoped `db_session` fixture yielding an `AsyncSession` bound to a rolled-back outer transaction, which also overrides `get_db`. Consumed by every DB test.

- [ ] **Step 1: Write the failing smoke test**

```python
# tests/test_harness_smoke.py
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

async def test_pgroonga_available(db_session):
    row = (await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname='pgroonga'")
    )).scalar_one_or_none()
    assert row == "pgroonga"
```

- [ ] **Step 2:** Run — expect FAIL (no `db_session` fixture / no container).
- [ ] **Step 3: Implement fixture in `conftest.py`**

```python
import asyncio
import pytest, pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("groonga/pgroonga:4.0.8-debian-17", driver="asyncpg") as pg:
        yield pg

@pytest_asyncio.fixture(scope="session")
async def _engine(pg_container):
    from alembic import command
    from alembic.config import Config
    url = pg_container.get_connection_url()
    cfg = Config("alembic.ini"); cfg.set_main_option("sqlalchemy.url", url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    eng = create_async_engine(url)
    yield eng
    await eng.dispose()

@pytest_asyncio.fixture
async def db_session(_engine):
    # outer transaction rolled back after each test; nested writes use savepoints
    conn = await _engine.connect()
    trans = await conn.begin()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = factory()
    # make the app's get_db yield THIS session
    from app.main import app
    from app.db import get_db
    async def _override():
        yield session
    app.dependency_overrides[get_db] = _override
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        await session.close()
        await trans.rollback()
        await conn.close()
```

Remove the old Tortoise `db` fixture. (Tests using `db` migrate to `db_session` in Phase 8.)

- [ ] **Step 4:** Run `pytest tests/test_harness_smoke.py -v` — expect PASS (Docker required).
- [ ] **Step 5:** Commit `test: real Postgres+PGroonga testcontainer harness with db_session fixture`.

---

# Phase 5 — Repositories

> Repositories are module-level functions taking `session` first. Reference task 15 shows one full write-model repo. Task 16 ports the other two existing repos. Task 17 adds the remaining write-model repos. Tasks 18–19 build read-model repos including the PGroonga rewrite. Each repo is exercised directly with the `db_session` fixture.

### Task 15: `agency` repository (reference write-model repo)

**Files:**
- Rewrite: `backend/app/repositories/agency.py` (functions gain `session` first arg)
- Test: `backend/tests/test_agency_repository.py`

**Interfaces:**
- Produces: `by_id(session, agency_id)`, `list_and_count(session, *, status, connection_type, search_text)`, `create(session, **fields)`, `save(session, agency, *, update_fields=None)`, `delete(session, agency)`, `increment_calls(session, agency)`, `count_all(session)` (same names/semantics as today, `session` added first).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agency_repository.py
import pytest
from app.repositories import agency as agency_repo
pytestmark = pytest.mark.asyncio

async def test_increment_calls_is_atomic(db_session):
    a = await agency_repo.create(db_session, name="A", total_calls=0)
    await db_session.flush()
    await agency_repo.increment_calls(db_session, a)
    assert a.total_calls == 1

async def test_list_and_count_filters_search(db_session):
    await agency_repo.create(db_session, name="Alpha")
    await agency_repo.create(db_session, name="Beta")
    await db_session.flush()
    rows, total = await agency_repo.list_and_count(
        db_session, status="all", connection_type=None, search_text="alph")
    assert total == 1 and rows[0].name == "Alpha"
```

- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3: Implement**

```python
from __future__ import annotations
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agency import Agency


async def by_id(session: AsyncSession, agency_id) -> Agency | None:
    return await session.get(Agency, agency_id)


async def list_and_count(session: AsyncSession, *, status, connection_type, search_text):
    stmt = select(Agency).order_by(Agency.name)
    if status != "all":
        stmt = stmt.where(Agency.status == status)
    if connection_type:
        stmt = stmt.where(Agency.connection_type == connection_type.upper())
    if search_text:
        stmt = stmt.where(Agency.name.ilike(f"%{search_text}%"))
    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )).scalar_one()
    return list(rows), total


async def create(session: AsyncSession, **fields) -> Agency:
    obj = Agency(**fields); session.add(obj); await session.flush(); return obj


async def save(session: AsyncSession, agency: Agency, *, update_fields=None) -> None:
    await session.flush()


async def delete(session: AsyncSession, agency: Agency) -> None:
    await session.delete(agency)


async def increment_calls(session: AsyncSession, agency: Agency) -> Agency:
    await session.execute(
        update(Agency).where(Agency.id == agency.id).values(total_calls=Agency.total_calls + 1)
    )
    await session.refresh(agency, attribute_names=["total_calls"])
    return agency


async def count_all(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Agency))).scalar_one()
```

- [ ] **Step 4:** Run — expect PASS.
- [ ] **Step 5:** Commit `feat(repo): agency repository on SQLAlchemy`.

### Task 16: `conversation` + `message` repositories

**Files:**
- Rewrite: `app/repositories/conversation.py`, `app/repositories/message.py`
- Test: `tests/test_conversation_repository.py`, `tests/test_message_repository.py`

Port every function from the inventory (§3), `session` first, using the idiom table. Key translations:
- `conversation.list_and_count`: `select(Conversation).where(Conversation.deleted_at.is_(None))`, optional `user_id`, `title.ilike`, `agencies.contains([agency])` (JSONB `@>`), `created_at >=/<`, `order_by(Conversation.created_at.desc())`, `.offset().limit()`; count via `order_by(None).subquery()`.
- `message.bulk_create(session, rows, ignore_conflicts)`: `pg_insert(Message).values(rows).on_conflict_do_nothing()`.
- `message.first_user_message(session, conversation_id)`: `select(Message).where(conversation_id==, role=="user").order_by(Message.created_at).limit(1)`.
- `message.set_category(session, message_id, category)`: `update(Message).where(id==).values(category=...)`.

- [ ] **Step 1:** Tests: create conv+messages, assert filter/pagination, bulk_create dedup, first_user_message.
- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** Implement both repos as `session`-first functions.
- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit `feat(repo): conversation + message repositories`.

### Task 17: Remaining write-model repos — llm, popular_question, connection_log, executive_brief, setting, evaluation, event

**Files:**
- Create: `app/repositories/{llm,popular_question,connection_log,executive_brief,setting,evaluation,event}.py`
- Test: one test file per repo

Move the ORM call sites currently in services (inventory §2) into `session`-first repo functions. Explicit per-repo function set:
- **llm.py**: `list_providers`, `create_provider`, `get_provider`, `update_provider(session, obj, data)`, `delete_provider`, `provider_has_routes(session, provider_id)`, `list_routes`, `route_purpose_exists`, `create_route`, `get_route`, `update_route`, `delete_route`. (`update_from_dict().save()` → `setattr` loop + flush.)
- **popular_question.py**: `visible_with_agency(session)` (selectinload agency, hidden==False), `all_with_agency(session)`, `text_key_exists`, `create`, `update`, `delete`, `bulk_create`.
- **connection_log.py**: `create`, `get`, `delete_older_than(session, cutoff)`; stats aggregation moves to the read-model repo (Task 18).
- **executive_brief.py**: `create(session, content, status)`, `latest(session)`.
- **setting.py**: `all(session)`, `get(session, key)`, `upsert(session, key, value, ...)`.
- **evaluation.py**: `all_golden_with_agency(session)`.
- **event.py**: `add(session, event_type, payload)`, `pending(session, limit)`, `mark_dispatched(session, event)`.

- [ ] **Step 1:** Per repo: a focused test (create + read-back + the one non-trivial query).
- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** Implement repos.
- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit per repo (`feat(repo): <name> repository`).

### Task 18: Read-model repos — analytics, connection-log stats, feedback, public-status

**Files:**
- Create: `app/repositories/analytics.py`, `app/repositories/feedback_read.py`, `app/repositories/public_status_read.py`
- Test: `tests/test_analytics_repo.py`, etc.

Move each raw-SQL / `RawSQL` / aggregation block from `services/analytics/{brief,dashboard,health,heatmap,usage}.py`, `services/feedback.py`, `services/public_status.py`, `services/connection_log.py` into `session`-first read-model functions that run `select(...)`/`text(...)`. Rules:
- Replace `conn.execute_query_dict(sql, [$1,...])` with `(await session.execute(text(sql_named), {...})).mappings().all()`, converting `$1`→`:name`.
- Replace `conn.execute_query("SET TIME ZONE ...")` with `await session.execute(text("SET LOCAL TIME ZONE :tz"), {"tz": settings.TIMEZONE})` at the top of the function (runs inside the caller's transaction).
- Replace `.annotate(x=RawSQL("..."))...group_by().values()` with a Core `select(func...., text("..."))`.

- [ ] **Step 1:** Tests seed messages/conversations/logs and assert the aggregate shapes (now runnable on real Postgres).
- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** Implement read-model functions.
- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit `feat(repo): analytics/feedback/public-status read models`.

### Task 19: `similarity` repository — pg_trgm → PGroonga (the semantic change)

**Files:**
- Create: `app/repositories/similarity.py`
- Rewrite: `app/services/similarity.py` (use the repo; drop `Tortoise`, drop the SQLite branch)
- Test: `tests/test_similarity_pgroonga.py`

**Interfaces:**
- Produces: `find_similar(session, query, cutoff) -> Message | None` and `answer_for(session, match) -> tuple[Message, ConnectionLog] | None`.

- [ ] **Step 1: Write the failing test** (real Postgres + PGroonga)

```python
import pytest
from datetime import datetime, timezone, timedelta
from app.repositories import similarity as similarity_repo
from app.repositories import conversation as conversation_repo
from app.repositories import message as message_repo
pytestmark = pytest.mark.asyncio

async def test_pgroonga_similar_search_finds_prior_question(db_session):
    conv = await conversation_repo.create(db_session, status="success", title="t")
    await message_repo.create(db_session, conversation_id=conv.id, role="user", content="ขอข้อมูลภาษี")
    await db_session.flush()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    match = await similarity_repo.find_similar(db_session, "ข้อมูลภาษี", cutoff)
    assert match is not None and "ภาษี" in match.content
```

- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3: Implement `find_similar` using `&@*` + `pgroonga_score`**

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.conversation import Message


async def find_similar(session: AsyncSession, query: str, cutoff):
    row = (await session.execute(text(
        """
        SELECT id, pgroonga_score(tableoid, ctid) AS score
        FROM messages
        WHERE role = 'user'
          AND created_at >= :cutoff
          AND content &@* :query
        ORDER BY score DESC
        LIMIT 1
        """
    ), {"cutoff": cutoff, "query": query})).mappings().first()
    if not row:
        return None
    return await session.get(Message, row["id"])
```
Rewrite `services/similarity.py`: `_similarity_search` → `similarity_repo.find_similar(session, ...)`; `_fetch_answer_by_match` → `similarity_repo.answer_for(session, match)` using a single `text()` join (Postgres-only, drop the `?`/SQLite branch); keep the `SIMILARITY_CACHE_ENABLED`/`SIMILARITY_THRESHOLD` gate but re-interpret threshold as a PGroonga-score floor (add `AND pgroonga_score(...) >= :floor` when `SIMILARITY_THRESHOLD > 0`). Leave a `# withinlazy: PGroonga score floor needs tuning; tokenizer/normalizer knob` comment. `find_similar_question` gains a `session` parameter.

- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit `feat(search): PGroonga similar-search replaces pg_trgm`.

---

# Phase 6 — Service & router rewiring

### Task 20: `events.publish(session, …)`; outbox stays transactional

**Files:**
- Modify: `app/services/events.py`, `app/services/agency_lifecycle.py:35` (caller), `app/services/chat/turn.py`
- Test: `tests/test_outbox_transactional.py`

- [ ] **Step 1: Write the failing test**

```python
import uuid
import pytest
from app.repositories import message as message_repo
from app.repositories import event as event_repo
pytestmark = pytest.mark.asyncio

async def test_turn_and_event_share_one_transaction(db_session):
    from app.services.chat import turn
    from app.services.events import publish
    conv_id = str(uuid.uuid4())
    await turn.save_turn(session=db_session, query="q", conversation_id=conv_id, answer="a",
                         references=[], category=None, agency_ids=[], response_time=1,
                         user=None, succeeded=True)
    await publish(db_session, "chat.turn_saved", {"conversation_id": conv_id})
    await db_session.flush()
    assert len(await message_repo.list_for_conversation(db_session, conv_id)) == 2
    assert len(await event_repo.pending(db_session, 10)) == 1  # same transaction
```

- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** Change `publish(event_type, payload)` → `publish(session, event_type, payload)` calling `event_repo.add(session, ...)`. Update the `agency_lifecycle` caller. Rewrite `turn.py`: drop `in_transaction()`, take `session`, call `conversation_repo`/`message_repo` and `publish(session, ...)`. **Streaming ruling:** the chat stream entrypoint that calls `save_turn` opens its own `async with AsyncSessionLocal() as session, session.begin():` and passes that session in (NOT the request `get_db` session). `dispatch_pending` opens its own `async with AsyncSessionLocal() as session, session.begin():`.
- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit `refactor(events): publish through the session; outbox commits with state`.

### Task 21: Rewire services to accept `session`

**Files:**
- Modify: every service in inventory §2 that used Tortoise (agency, connection_log, feedback, popular_questions, public_status, similarity, settings, evaluation, llm/admin, analytics/*, chat/*).
- Test: existing service tests (ported in Phase 7) + targeted new ones.

Procedure per service: add a `session` parameter to the entry functions the routers call; replace direct ORM/`tortoise` calls with `<repo>.<fn>(session, ...)`; delete all `from tortoise...` imports. Verify `grep -rn "tortoise" app/services` is empty at the end.

- [ ] **Step 1–4:** Per service, adjust its test to pass `session` (`db_session` fixture), run red→green.
- [ ] **Step 5:** Commit per service group (`refactor(service): route <name> through session`).

### Task 22: Routers depend on `get_db` and pass `session` to services

**Files:**
- Modify: `app/routers/**` (24 files) — add `session: AsyncSession = Depends(get_db)` and forward to services.
- Test: existing router tests (Phase 7).

- [ ] **Step 1:** Pick one router (agencies/crud.py), add the dependency, thread `session` into `agency_service` calls; run its test.
- [ ] **Step 2–4:** Repeat per router; the request transaction commits at request end.
- [ ] **Step 5:** Commit per router group.

### Task 23: Non-request entry points — scheduler, MCP, seed, scripts

**Files:**
- Modify: `app/scheduler.py`, `app/mcp/server.py:85`, `app/services/llm/seed.py`, `app/services/seed.py`, `backend/scripts/seed.py`, `backend/scripts/hash_existing_api_keys.py`
- Test: `tests/test_scheduler_health.py` (exists), `tests/test_mcp_*` (exist)

- [ ] **Step 1:** scheduler jobs wrap work in `async with AsyncSessionLocal() as session, session.begin():` (health check `connection_log.create`, `agency` list, retention `connection_log.delete_older_than`, `dispatch_pending`).
- [ ] **Step 2:** `mcp/server.py._fetch_agencies` uses `async with AsyncSessionLocal() as session, session.begin(): rows = await agency_repo.list_for_mcp(session, ...)` (add a read function returning the same `.values(...)` dict shape).
- [ ] **Step 3:** `scripts/seed.py` replaces `Tortoise.init/close_connections` with `async with AsyncSessionLocal() as session, session.begin():`. `hash_existing_api_keys.py`: swap Tortoise init for `AsyncSessionLocal`; **leave the pre-existing `UserAPIKey` staleness untouched** (out of scope — flag in commit body).
- [ ] **Step 4:** Run the affected existing tests — expect PASS.
- [ ] **Step 5:** Commit `refactor: non-request contexts open their own session`.

---

# Phase 7 — Startup wiring

### Task 30: `db.py` init/close + `main.py` lifespan + delete `database.py`

**Files:**
- Modify: `app/db.py` (add `run_migrations()` + `init_db()`), `app/main.py:86-95`, `app/config.py:187` (`load_settings_from_db` uses a session)
- Delete: `app/database.py`
- Test: `tests/test_startup_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
pytestmark = pytest.mark.asyncio

async def test_init_db_runs_migrations_then_seeds(monkeypatch):
    import app.db as db
    calls = []

    async def _fake_migrations():
        calls.append("migrate")

    async def _fake_seed(session):
        calls.append("seed")

    monkeypatch.setattr(db, "run_migrations", _fake_migrations)
    monkeypatch.setattr("app.services.llm.seed.seed_llm_defaults", _fake_seed)
    await db.init_db()
    assert calls == ["migrate", "seed"]  # migrations first, then seed; no generate_schemas
```

- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** In `db.py` add:
```python
async def run_migrations() -> None:
    import asyncio
    from alembic import command
    from alembic.config import Config
    cfg = Config("alembic.ini"); cfg.set_main_option("sqlalchemy.url", database_url(settings))
    await asyncio.to_thread(command.upgrade, cfg, "head")

async def init_db() -> None:
    await run_migrations()
    from app.services.llm.seed import seed_llm_defaults
    async with AsyncSessionLocal() as session, session.begin():
        await seed_llm_defaults(session)
```
Update `main.py` to import `init_db`/`close_db` from `app.db`. Delete `app/database.py`. Update `load_settings_from_db` to open `async with AsyncSessionLocal() as session, session.begin():` and call `setting_repo.all(session)`.
- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit `feat(db): Alembic-driven startup; drop database.py + generate_schemas`.

---

# Phase 8 — Test port sweep & Tortoise removal

### Task 40: Port the ~30 `db`-fixture tests to `db_session`

**Files:**
- Modify: the ~30 test files that used the old `db` fixture.

Per-file procedure (mechanical, apply the idiom table):
- Replace the `db` fixture param with `db_session`.
- Replace direct model calls (`await Agency.create(...)`) with repo calls (`await agency_repo.create(db_session, ...)`) or seed via `db_session.add(...)` + `flush`.
- Replace `await Model.filter(...)` assertions with repo/`session` queries.
- Router tests using the FastAPI `app` already get the overridden `get_db` from the `db_session` fixture — assert against `db_session` after the request.

- [ ] **Step 1:** Port 5 files, run that subset green.
- [ ] **Step 2–4:** Continue in batches of ~5, `pytest -q` after each batch.
- [ ] **Step 5:** Commit per batch (`test: port <area> tests to db_session fixture`).

### Task 41: Full suite green

- [ ] **Step 1:** `cd backend && python -m pytest -q`
- [ ] **Step 2:** Fix stragglers (timestamp/enum/JSON assertions per the risks list).
- [ ] **Step 3:** `grep -rn "tortoise" backend/app backend/tests` → **must be empty**.
- [ ] **Step 4:** Commit `test: full suite green on SQLAlchemy + PGroonga`.

### Task 42: Delete Aerich artifacts

**Files:**
- Delete: `backend/migrations/` (entire Aerich tree)

- [ ] **Step 1:** `git rm -r backend/migrations`
- [ ] **Step 2:** `grep -rn "aerich" backend/` → empty.
- [ ] **Step 3:** `cd backend && alembic upgrade head` on a clean DB still works.
- [ ] **Step 4:** Commit `chore: remove Aerich migrations (superseded by Alembic baseline)`.

---

# Phase 9 — Validation & finalize

### Task 45: Docker compose end-to-end

- [ ] **Step 1:** `docker compose down -v && docker compose up -d --build`
- [ ] **Step 2:** Confirm backend starts: Alembic upgrade runs, seeds load, `/health` returns `ok`.
- [ ] **Step 3:** Smoke a chat turn + an analytics endpoint + the similarity cache (PGroonga path) against the running stack.
- [ ] **Step 4:** `docker compose logs backend` clean (no ORM errors).

### Task 46: CONTEXT.md + final commit

- [ ] **Step 1:** Update `CONTEXT.md` with the migration outcome (per project rule).
- [ ] **Step 2:** `git add CONTEXT.md && git commit -m "docs: record SQLAlchemy/Alembic/PGroonga migration"`.
- [ ] **Step 3:** Open PR from `refactor/sqlalchemy-migration`.

---

## Self-review notes (author)

- **Spec coverage:** models (§3→Ph2), session/get_db (§4→Ph1 Task3), full repo layer incl read-models (§5→Ph5), PGroonga (§6→Task19/0/9), Alembic baseline (§7→Ph3), startup/config (§8→Ph1/Task30), testcontainers (§9→Ph4/8), risks (§10→Task41). All mapped.
- **Extra vs spec (found in inventory):** FK relations + ondelete; `Conversation.metadata`→`meta` attribute rename; `Setting`/`RateLimitCounter` non-`id` PKs; `bulk_create`/`prefetch`/`update_from_dict`; stale `UserAPIKey` script left as-is. Documented in the tasks.
- **Seam:** `get_db` dependency owns one transaction per request (`session.begin()`); repos are `session`-first module functions; services never commit; streaming persistence uses its own `AsyncSessionLocal`.
- **Type consistency:** repo function names match across services and tests (`by_id`, `list_and_count`, `create`, `save`, `delete`, `increment_calls`, `find_similar`, `event.add/pending/mark_dispatched`), all with `session` as first parameter.
