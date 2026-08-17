# Replace Redis with Postgres Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Redis with Postgres for auth session storage and LLM-provider rate limiting, then remove the Redis service, dependency, and config.

**Architecture:** Two new Tortoise models (`Session`, `RateLimitCounter`) back the rewritten `auth_session.py` and `rate_limit.py`. The existing `RateLimiter` protocol and all call sites stay unchanged. The rate limiter becomes a fixed-window counter using an atomic `INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING` upsert that runs on both Postgres and SQLite. Fail mode is fail-closed: a DB error returns `(allowed=False, retry_after=1)` so the existing `_acquire` retry loop turns outages into backpressure. Redis code, tests, dependency, and docker-compose service are deleted last.

**Tech Stack:** Python, FastAPI, Tortoise ORM 0.25.4, asyncpg, in-memory SQLite 3.45.1 for tests, pytest.

**Spec:** `docs/superpowers/specs/2026-08-17-redis-to-postgres-design.md`

## Global Constraints

- Backend code lives under `backend/app`. Run tests from `backend/` with `.venv/bin/python -m pytest`.
- Test DB is the function-scoped `db` fixture in `backend/tests/conftest.py`: in-memory SQLite, `Tortoise.generate_schemas()` from registered models. New models are auto-discovered once added to `app/models/__init__.py`.
- Follow existing patterns: raw SQL via `async with in_transaction() as conn:` then `conn.execute_query()` / `conn.execute_query_dict()` (see `app/services/similarity.py`, `app/services/analytics/dashboard.py`). Model files follow `app/models/user.py` (UUID PK via `generate_uuid`, `now()` helper, `Meta.table`).
- `app/utils/__init__.py` exports `generate_uuid7()` (returns `uuid.UUID`), `generate_uuid()` (alias), `now()` (timezone-aware `datetime`), and `get_tz()`.
- Naming: American English, no plural "xxxList". Full English, no alias.
- TDD mandatory: failing test → confirm fail → minimal code → confirm pass → refactor. No exceptions.
- Prose in commits and docs uses ASD-STE100 Simplified Technical English.
- One commit per task unless a task has explicit commit steps. Commit message format: `<type>: <subject>` with a `Co-Authored-By: Claude <noreply@anthropic.com>` trailer.

---

## File Structure

**Create:**
- `backend/app/models/session.py` — `Session` model (opaque id → user, `expires_at`).
- `backend/app/models/rate_limit_counter.py` — `RateLimitCounter` model (key + window_start → count).
- `backend/tests/services/test_auth_session.py` — rewritten session tests (overwrites the existing file).
- `backend/tests/test_rate_limit.py` — new Postgres fixed-window limiter tests.

**Modify:**
- `backend/app/models/__init__.py` — register the two new models.
- `backend/app/services/auth_session.py` — rewrite backend to Tortoise ORM; delete `_InProcessSessions`, `_RedisSessions`.
- `backend/app/services/rate_limit.py` — rewrite to `PostgresFixedWindowLimiter`; delete Redis classes, Lua, `RedisHealth`.
- `backend/app/config.py` — delete `REDIS_URL`, `REDIS_SOCKET_TIMEOUT_MS`.
- `backend/pyproject.toml` — remove `redis>=5.0.0` dependency.
- `docker-compose.yaml` — delete the `redis` service, volume, env, `depends_on`.

**Delete:**
- `backend/tests/test_redis_rate_limit.py`
- `backend/tests/test_redis_health.py`
- `backend/tests/test_fail_open_observability.py`
- `backend/tests/test_rate_limit_degrade.py`
- `backend/tests/test_limiter_factory.py`

---

## Task 1: `RateLimitCounter` model

**Files:**
- Create: `backend/app/models/rate_limit_counter.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/models/test_rate_limit_counter.py` (create the `tests/models/` dir if it has no `__init__.py`; mirror existing test dir layout — check first)

**Interfaces:**
- Consumes: `from tortoise import fields`, `from tortoise.models import Model`.
- Produces: `RateLimitCounter` model registered in `app.models`, table `rate_limit_counters`, fields `id` (BigIntField PK), `key` (CharField 128), `window_start` (BigIntField), `count` (IntField default 0), `Meta.unique_together = (("key", "window_start"),)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/models/test_rate_limit_counter.py
import pytest

from app.models.rate_limit_counter import RateLimitCounter


@pytest.mark.asyncio
async def test_counter_create_and_unique_constraint(db):
    await RateLimitCounter.create(key="llm:openrouter:s", window_start=1000, count=1)
    row = await RateLimitCounter.get(key="llm:openrouter:s", window_start=1000)
    assert row.count == 1


@pytest.mark.asyncio
async def test_counter_unique_together_blocks_duplicate(db):
    from tortoise.exceptions import IntegrityError

    await RateLimitCounter.create(key="llm:openrouter:s", window_start=1000, count=1)
    with pytest.raises(IntegrityError):
        await RateLimitCounter.create(key="llm:openrouter:s", window_start=1000, count=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/models/test_rate_limit_counter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.rate_limit_counter'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/rate_limit_counter.py
"""Fixed-window rate-limit counter: one row per (key, window_start)."""
from tortoise import fields
from tortoise.models import Model


class RateLimitCounter(Model):
    id = fields.BigIntField(primary_key=True)
    key = fields.CharField(max_length=128)
    window_start = fields.BigIntField()          # epoch microseconds, window-floored
    count = fields.IntField(default=0)

    class Meta:
        table = "rate_limit_counters"
        unique_together = (("key", "window_start"),)
```

Register it. Add to `backend/app/models/__init__.py`:

```python
from .rate_limit_counter import *
```

(Place the import in alphabetical order within the existing list.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/models/test_rate_limit_counter.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/rate_limit_counter.py backend/app/models/__init__.py backend/tests/models/test_rate_limit_counter.py
git commit -m "feat(rate-limit): add RateLimitCounter model for fixed-window counters

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: `PostgresFixedWindowLimiter`

**Files:**
- Create: none (added to existing file)
- Modify: `backend/app/services/rate_limit.py` — but only the new limiter class for now; the Redis code is deleted in Task 5. To keep the build green, add `PostgresFixedWindowLimiter` alongside the existing classes.
- Test: `backend/tests/test_rate_limit.py` (new)

**Interfaces:**
- Consumes: `from app.models.rate_limit_counter import RateLimitCounter` (Task 1); `from tortoise.transactions import in_transaction`; `from tortoise import connections`.
- Produces: `PostgresFixedWindowLimiter` with `async check(key: str, *, limit: int, window_s: float = 60.0) -> RateLimitResult`. `RateLimitResult` already exists in `rate_limit.py` (NamedTuple `allowed: bool`, `retry_after: int`). Also `LimiterHealth` (tracks healthy→failing; logs once).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_rate_limit.py
import logging

import pytest

import app.services.rate_limit as rl
from app.services.rate_limit import (
    PostgresFixedWindowLimiter,
    RateLimitResult,
)


@pytest.mark.asyncio
async def test_under_limit_increments_and_allows(db):
    lim = PostgresFixedWindowLimiter()
    r = await lim.check("llm:p:s", limit=3, window_s=1.0)
    assert r == RateLimitResult(True, 0)


@pytest.mark.asyncio
async def test_at_limit_denies_with_retry_after_in_window(db):
    lim = PostgresFixedWindowLimiter()
    for _ in range(3):
        assert await lim.check("llm:p:s", limit=3, window_s=60.0) == RateLimitResult(True, 0)
    r = await lim.check("llm:p:s", limit=3, window_s=60.0)
    assert r.allowed is False
    assert 1 <= r.retry_after <= 60


@pytest.mark.asyncio
async def test_zero_limit_short_circuits_no_write(db):
    from app.models.rate_limit_counter import RateLimitCounter

    lim = PostgresFixedWindowLimiter()
    assert await lim.check("llm:p:s", limit=0, window_s=60.0) == RateLimitResult(True, 0)
    assert await RateLimitCounter.filter(key="llm:p:s").count() == 0


@pytest.mark.asyncio
async def test_new_window_resets_counter(db):
    lim = PostgresFixedWindowLimiter()
    # Fill a window far in the past; prune must drop it and allow again.
    from app.models.rate_limit_counter import RateLimitCounter
    await RateLimitCounter.create(key="llm:p:s", window_start=1, count=3)

    r = await lim.check("llm:p:s", limit=3, window_s=60.0)
    assert r == RateLimitResult(True, 0)


@pytest.mark.asyncio
async def test_db_error_fails_closed_and_logs_once(db, monkeypatch, caplog):
    lim = PostgresFixedWindowLimiter()
    rl._limiter_health.failing = False
    rl._limiter_health.degraded_total = 0

    async def boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(rl, "_upsert_and_count", boom)

    with caplog.at_level(logging.WARNING, logger="app.services.rate_limit"):
        r1 = await lim.check("llm:p:s", limit=3, window_s=60.0)
        r2 = await lim.check("llm:p:s", limit=3, window_s=60.0)
    assert r1 == RateLimitResult(False, 1)
    assert r2 == RateLimitResult(False, 1)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "rate limit" in warnings[0].getMessage().lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rate_limit.py -v`
Expected: FAIL with `ImportError: cannot import name 'PostgresFixedWindowLimiter'`.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/services/rate_limit.py` (above `build_limiter`):

```python
import math

from tortoise import connections
from tortoise.transactions import in_transaction

from app.models.rate_limit_counter import RateLimitCounter


class LimiterHealth:
    """Fail-closed outage tracker. Logs once on healthy -> failing."""

    def __init__(self):
        self.failing = False
        self.degraded_total = 0
        self._since = 0

    def record_failure(self) -> bool:
        self.degraded_total += 1
        if not self.failing:
            self.failing = True
            self._since = self.degraded_total - 1
            return True
        return False


_limiter_health = LimiterHealth()


async def _upsert_and_count(key: str, window_start: int) -> int:
    """Atomic fixed-window increment. Returns the new count for this window."""
    conn = connections.get("default")
    rows = await conn.execute_query_dict(
        """
        INSERT INTO rate_limit_counters (key, window_start, count)
        VALUES ($1, $2, 1)
        ON CONFLICT (key, window_start)
        DO UPDATE SET count = count + 1
        RETURNING count
        """,
        [key, window_start],
    )
    return int(rows[0]["count"])


class PostgresFixedWindowLimiter:
    """Fixed-window limiter backed by the rate_limit_counters table.

    One atomic upsert per check. Fail-closed: a DB error returns
    (False, 1) so the caller's retry loop turns outages into backpressure.
    """

    async def check(
        self, key: str, *, limit: int, window_s: float = 60.0
    ) -> RateLimitResult:
        if limit <= 0:
            return RateLimitResult(True, 0)
        window_us = int(window_s * 1_000_000)
        now_us = int(time.time() * 1_000_000)
        window_start = now_us - (now_us % window_us)
        try:
            async with in_transaction() as conn:
                await conn.execute_query(
                    "DELETE FROM rate_limit_counters WHERE key = $1 AND window_start < $2",
                    [key, window_start],
                )
            count = await _upsert_and_count(key, window_start)
        except Exception as exc:  # noqa: BLE001 — fail-closed on any DB error
            if _limiter_health.record_failure():
                logger.warning(
                    "rate limit: datastore unavailable, failing closed "
                    "(provider calls will back off and retry)",
                    exc_info=exc,
                )
            return RateLimitResult(False, 1)
        if count <= limit:
            return RateLimitResult(True, 0)
        retry_us = window_start + window_us - now_us
        retry_after = max(1, math.ceil(retry_us / 1_000_000))
        return RateLimitResult(False, retry_after)
```

Note: the `$1, $2` placeholders are asyncpg style. SQLite's test path — see Step 4 note.

- [ ] **Step 4: Run test to verify it passes — dialect placeholder fix**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rate_limit.py -v`

If the SQLite test path rejects `$1` placeholders (SQLite expects `?`), replace the raw SQL with Tortoise's ORM `update_or_create` + `filter().delete()` path, OR detect the dialect and substitute placeholders. The laziest correct fix that keeps a single code path: use the ORM for prune and a Tortoise `Q`-based upsert:

```python
# Replace _upsert_and_count with a dialect-safe ORM version:
async def _upsert_and_count(key: str, window_start: int) -> int:
    counter, _ = await RateLimitCounter.update_or_create(
        key=key, window_start=window_start, defaults={"count": 0}
    )
    counter.count += 1
    await counter.save(update_fields=["count"])
    return counter.count
```

and prune via:

```python
await RateLimitCounter.filter(key=key, window_start__lt=window_start).delete()
```

Use the ORM version if the `$N` placeholders fail under SQLite; it runs identically on Postgres. Pick whichever passes first; record the choice in the commit message.

Expected after the fix: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/rate_limit.py backend/tests/test_rate_limit.py
git commit -m "feat(rate-limit): add PostgresFixedWindowLimiter (fixed-window, fail-closed)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: `Session` model + rewritten `auth_session` service

**Files:**
- Create: `backend/app/models/session.py`
- Modify: `backend/app/models/__init__.py`, `backend/app/services/auth_session.py`
- Test: `backend/tests/services/test_auth_session.py` (overwrites existing)

**Interfaces:**
- Consumes: `from app.utils import generate_uuid7, now`; `from app.config import settings`; `from tortoise import fields`, `Model`.
- Produces: `Session` model (table `sessions`): `id` CharField(64) PK, `user` ForeignKeyField to `models.User` null=True, `expires_at` DatetimeField indexed, `created_at` auto_now_add. Service functions (signatures unchanged): `async create_session(user_id: str) -> str`, `async resolve_session(session_id: str) -> str | None`, `async delete_session(session_id: str) -> None`, `async expire_session(session_id: str, ttl: int) -> None`, `async remaining_ttl(session_id: str) -> int | None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/test_auth_session.py
from datetime import timedelta

import pytest

from app.services.auth_session import (
    create_session, delete_session, expire_session, remaining_ttl, resolve_session,
)
from app.utils import now


@pytest.mark.asyncio
async def test_create_and_resolve_roundtrip(db, make_user):
    user = await make_user()
    sid = await create_session(str(user.id))
    assert sid
    assert await resolve_session(sid) == str(user.id)


@pytest.mark.asyncio
async def test_expired_session_returns_none_and_is_deleted(db, make_user):
    from app.models.session import Session

    user = await make_user()
    sid = await create_session(str(user.id))
    # Force expiry in the past.
    await Session.filter(id=sid).update(expires_at=now() - timedelta(seconds=1))
    assert await resolve_session(sid) is None
    assert await Session.filter(id=sid).count() == 0


@pytest.mark.asyncio
async def test_delete_session_removes_row(db, make_user):
    user = await make_user()
    sid = await create_session(str(user.id))
    await delete_session(sid)
    assert await resolve_session(sid) is None


@pytest.mark.asyncio
async def test_expire_session_shortens_ttl_and_still_resolves(db, make_user):
    user = await make_user()
    sid = await create_session(str(user.id))
    await expire_session(sid, 5)
    ttl = await remaining_ttl(sid)
    assert ttl is not None and ttl <= 5
    assert await resolve_session(sid) == str(user.id)


@pytest.mark.asyncio
async def test_remaining_ttl_none_for_missing(db):
    assert await remaining_ttl("does-not-exist") is None


@pytest.mark.asyncio
async def test_delete_and_expire_on_missing_sid_are_noops(db):
    await delete_session("missing")          # no raise
    await expire_session("missing", 5)       # no raise
```

The `make_user` helper: if `backend/tests/conftest.py` has no such fixture, define a local one in the test file (a User with a unique email). Check conftest first; reuse if present.

```python
# Add at top of the test file if no fixture exists:
from app.models.user import User


@pytest.fixture
async def make_user(db):
    async def _make():
        return await User.create(
            email="u@example.com", hashed_password="x", role="user"
        )
    return _make
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_auth_session.py -v`
Expected: FAIL with `ImportError` for `app.models.session` (the test imports it).

- [ ] **Step 3: Write the model**

```python
# backend/app/models/session.py
"""Opaque server-side session store: session id -> user, with expiry."""
from tortoise import fields
from tortoise.models import Model


class Session(Model):
    id = fields.CharField(max_length=64, primary_key=True)  # generate_uuid7().hex
    user = fields.ForeignKeyField("models.User", related_name="sessions", null=True)
    expires_at = fields.DatetimeField(index=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "sessions"
```

Register in `backend/app/models/__init__.py` (alphabetical):

```python
from .session import *
```

- [ ] **Step 4: Write the rewritten service**

Replace the entire contents of `backend/app/services/auth_session.py`:

```python
"""Opaque server-side session store backed by Postgres (Session model)."""
from datetime import timedelta

from app.config import settings
from app.models.session import Session
from app.utils import generate_uuid7, now


def _ttl_seconds() -> int:
    return settings.SESSION_TTL_MINUTES * 60


async def create_session(user_id: str) -> str:
    sid = generate_uuid7().hex
    await Session.create(id=sid, user_id=user_id, expires_at=now() + timedelta(seconds=_ttl_seconds()))
    return sid


async def resolve_session(session_id: str) -> str | None:
    session = await Session.get_or_none(id=session_id)
    if session is None:
        return None
    # withinlazy: lazy-delete only; add a periodic DELETE ... WHERE
    # expires_at <= now() reaper if the sessions table grows past a ceiling.
    if session.expires_at <= now():
        await session.delete()
        return None
    return str(session.user_id)


async def delete_session(session_id: str) -> None:
    await Session.filter(id=session_id).delete()


async def expire_session(session_id: str, ttl: int) -> None:
    """Reset a session's expiry to ``ttl`` seconds from now (rotation grace)."""
    await Session.filter(id=session_id).update(expires_at=now() + timedelta(seconds=ttl))


async def remaining_ttl(session_id: str) -> int | None:
    session = await Session.get_or_none(id=session_id)
    if session is None or session.expires_at <= now():
        return None
    return max(0, int((session.expires_at - now()).total_seconds()))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_auth_session.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/session.py backend/app/models/__init__.py backend/app/services/auth_session.py backend/tests/services/test_auth_session.py
git commit -m "feat(session): move auth sessions to Postgres Session model

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Wire `build_limiter` to Postgres + config removal

**Files:**
- Modify: `backend/app/services/rate_limit.py` (the `build_limiter` function), `backend/app/config.py`, `backend/pyproject.toml`, `docker-compose.yaml`
- Test: extend `backend/tests/test_rate_limit.py`

**Interfaces:**
- Consumes: `PostgresFixedWindowLimiter` (Task 2).
- Produces: `build_limiter()` returns `PostgresFixedWindowLimiter()` always (no `url` param). `REDIS_URL` / `REDIS_SOCKET_TIMEOUT_MS` removed from `Settings`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_rate_limit.py`:

```python
from app.services.rate_limit import build_limiter, PostgresFixedWindowLimiter


def test_factory_returns_postgres_limiter():
    lim = build_limiter()
    assert isinstance(lim, PostgresFixedWindowLimiter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rate_limit.py::test_factory_returns_postgres_limiter -v`
Expected: FAIL — `build_limiter` still returns `RedisSlidingWindowLimiter` / `InProcessLimiter` based on `url`.

- [ ] **Step 3: Rewrite `build_limiter` and remove `close_limiter_client`**

In `backend/app/services/rate_limit.py`, replace the `build_limiter` function and delete `close_limiter_client` (no async client to close now) plus the module-level `_redis_client`:

```python
def build_limiter():
    """Return the Postgres-backed limiter (the only backend)."""
    return PostgresFixedWindowLimiter()
```

Also check `app/main.py` for any call to `close_limiter_client()` on shutdown — if present, remove that shutdown hook (grep first).

- [ ] **Step 4: Remove Redis config from Settings**

In `backend/app/config.py`, delete the Redis block:

```python
    # ── Redis (shared LLM-provider throttle budget across workers) ───────────
    REDIS_URL: str = ""           # empty = in-process limiter (single worker)
    REDIS_SOCKET_TIMEOUT_MS: int = 100
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rate_limit.py -v`
Expected: PASS (all, including the new factory test).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/rate_limit.py backend/app/config.py backend/tests/test_rate_limit.py
# also app/main.py if the shutdown hook was removed:
git add backend/app/main.py
git commit -m "refactor(rate-limit): wire build_limiter to Postgres; remove Redis config

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Delete Redis code, tests, dependency, and docker service

**Files:**
- Delete: 5 Redis test files (listed below)
- Modify: `backend/app/services/rate_limit.py` (delete `SlidingWindowLimiter`, `InProcessLimiter`, `RedisHealth`, `RedisSlidingWindowLimiter`, the Lua script, `_redis_health`, `_fallback_limiter`), `backend/pyproject.toml`, `docker-compose.yaml`

**Interfaces:**
- Consumes: nothing new.
- Produces: a codebase with no Redis references.

- [ ] **Step 1: Delete the Redis test files**

```bash
git rm backend/tests/test_redis_rate_limit.py \
       backend/tests/test_redis_health.py \
       backend/tests/test_fail_open_observability.py \
       backend/tests/test_rate_limit_degrade.py \
       backend/tests/test_limiter_factory.py
```

- [ ] **Step 2: Delete the Redis limiter code**

In `backend/app/services/rate_limit.py`, remove everything Redis-specific so only this remains (plus the Task 2 additions):

- Keep: imports needed for `PostgresFixedWindowLimiter` (`time`, `math`, `logging`, `trace`, `uuid` if used), `RateLimitResult`, `RateLimiter` Protocol, `LimiterHealth`, `_limiter_health`, `_upsert_and_count`, `PostgresFixedWindowLimiter`, `build_limiter`.
- Delete: `SlidingWindowLimiter`, `InProcessLimiter`, `RedisHealth`, `_SLIDING_WINDOW_LUA`, `_redis_health`, `_fallback_limiter`, `RedisSlidingWindowLimiter`, `_redis_client`, `_get_redis_client`, `close_limiter_client`, and the now-unused `from collections import defaultdict, deque` and `from redis.exceptions import RedisError` imports.

The `RateLimiter` Protocol stays — `llm/client.py` type-hints against it. Confirm the file still defines `RateLimiter` and `RateLimitResult`.

- [ ] **Step 3: Remove the redis dependency**

In `backend/pyproject.toml`, delete the line:

```toml
    "redis>=5.0.0",
```

- [ ] **Step 4: Remove the redis service from docker-compose**

In `docker-compose.yaml`, delete:
- The entire `redis:` service block (image, healthcheck, volume).
- The `redis_data:` volume entry under `volumes:`.
- The `REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}` env line under the backend service.
- The `- redis:` entry under the backend service `depends_on:`.

Then validate:

```bash
docker compose config >/dev/null && echo "valid"
```
Expected: `valid`.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass (baseline was 852 pass / 6 skip; the 5 deleted Redis test files are gone, the new session + rate-limit tests are in). No import of `redis` anywhere.

- [ ] **Step 6: Verify no Redis references remain**

Run: `grep -rniE 'redis' backend/app docker-compose.yaml --include='*.py' --include='*.yaml'`
Expected: no matches. (Check `.github/workflows/test.yml` too — if it sets `REDIS_URL` or runs a redis service, clean that up here.)

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove Redis — sessions and rate limiting now use Postgres

Deletes the redis service, dependency, config, and all Redis-backed code.
One backend datastore remains (Postgres). The rate limiter is fail-closed;
the auth session store uses the Session model with lazy-delete expiry.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Final verification + CONTEXT.md update

**Files:**
- Modify: `CONTEXT.md`

**Interfaces:** none.

- [ ] **Step 1: Full suite, clean**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass. Record the pass/skip count.

- [ ] **Step 2: Surface-parity sanity**

Run: `cd backend && .venv/bin/python -m pytest tests/test_surface_parity.py -q`
Expected: PASS (no route changed).

- [ ] **Step 3: Update CONTEXT.md**

Append a dated section to `CONTEXT.md` (lowercase, as the repo tracks it) summarizing this change in ASD-STE100: Redis removed; sessions → Postgres `Session` model; rate limit → Postgres `RateLimitCounter` fixed-window, fail-closed; redis service/dependency/config deleted; test counts.

- [ ] **Step 4: Commit**

```bash
git add CONTEXT.md
git commit -m "docs(context): record Redis-to-Postgres consolidation

Co-Authored-By: Claude <noreply@anthropic.com>"
```
