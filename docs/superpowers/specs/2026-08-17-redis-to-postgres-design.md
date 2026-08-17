# Design — Replace Redis with Postgres (2026-08-17)

Written in Simplified Technical English. This is the design spec for replacing
Redis with Postgres as the single backend datastore for the two ephemeral
concerns Redis currently serves: auth session storage and LLM-provider rate
limiting.

## Goal

Remove Redis entirely. Move both auth sessions and LLM-provider rate limiting to
Postgres. One backend datastore. Delete the Redis service from
`docker-compose.yaml`, the `redis` dependency, and the Redis config.

## Decisions (locked)

- **Scope:** Replace both sessions and rate limiting. Drop Redis.
- **Rate-limit algorithm:** Fixed-window counter. Atomic
  `INSERT ... ON CONFLICT ... DO UPDATE` upsert per `(key, window_start)`.
- **Fail mode:** Fail-closed. A Postgres error makes the limiter return
  `(allowed=False, retry_after=1)`. The LLM client's existing retry loop turns
  this into backpressure; no new error kind.
- **Session expiry cleanup:** Lazy delete on read. No background reaper.
- **Session id:** `generate_uuid7().hex` (time-ordered, reuses the existing
  util in `app/utils/uuid7.py`).
- **Code shape:** Swap backends in place behind the existing module boundaries.
  No new repository interface (one implementation; the lazy rule forbids the
  abstraction).

## What stays

- Module boundaries: `app/services/auth_session.py`, `app/services/rate_limit.py`.
- The `RateLimiter` protocol (`async check(key, *, limit, window_s) ->
  RateLimitResult`).
- Every call site, unchanged:
  - `app/routers/auth.py` (login, logout, anonymous).
  - `app/auth/ws.py` (WebSocket session resolution).
  - `app/middleware/session_refresh.py` (rotation: reads `remaining_ttl`, calls
    `expire_session` for the grace window).
  - `app/services/llm/client.py` (`_acquire` calls `_provider_limiter.check`).
- The Postgres datastore, the asyncpg pool, the Tortoise ORM, and the in-memory
  SQLite test schema generation. No new infra.

## Data model

Two new Tortoise models, following the existing `User` pattern (UUID PK where
applicable, `app.utils` helpers, `Meta.table`). Registered in
`app/models/__init__.py` so Tortoise discovers them and generates the schema.

### `Session` — `app/models/session.py`, table `sessions`

- `id` — `CharField(max_length=64), primary_key=True`. The opaque session id,
  `generate_uuid7().hex`. CharField, not UUIDField: the value is an opaque hex
  token, not a relationship target.
- `user` — `ForeignKeyField("models.User", related_name="sessions",
  null=True)`. Nullable because anonymous sessions (users with
  `is_ephemeral=True`) also create sessions.
- `expires_at` — `DatetimeField(index=True)`. Indexed for the lazy-delete
  filter.
- `created_at` — `DatetimeField(auto_now_add=True)`.

### `RateLimitCounter` — `app/models/rate_limit_counter.py`, table `rate_limit_counters`

- `id` — `BigIntField(primary_key=True)`.
- `key` — `CharField(max_length=128)` (for example, `llm:openrouter:s`).
- `window_start` — `BigIntField`. Epoch microseconds aligned to the window
  floor: `now_us - (now_us % window_us)`.
- `count` — `IntField`.
- Unique constraint on `(key, window_start)` — the conflict target for the
  upsert.

Growth is bounded by `(distinct keys) x (active windows)`: a handful of
provider keys, trivial.

## Components and data flow

### `app/services/auth_session.py` (rewritten backend, same public functions)

The five functions keep their signatures. All are `async` and use Tortoise ORM
directly. The `_InProcessSessions` and `_RedisSessions` classes are deleted.

- `create_session(user_id) -> str`:
  `sid = generate_uuid7().hex`;
  `expires_at = now() + SESSION_TTL_MINUTES * 60`;
  `await Session.create(id=sid, user_id=user_id, expires_at=expires_at)`;
  return `sid`.
- `resolve_session(session_id) -> str | None`:
  `session = await Session.get_or_none(id=session_id)`;
  if `None`, return `None`;
  if `expires_at <= now()`, delete the row and return `None` (lazy delete);
  else return `str(session.user_id)`.
- `delete_session(session_id) -> None`:
  `await Session.filter(id=session_id).delete()`.
- `expire_session(session_id, ttl) -> None`:
  shorten the row's `expires_at` to `now() + ttl` (the grace window):
  `await Session.filter(id=session_id).update(expires_at=now() + ttl)`.
- `remaining_ttl(session_id) -> int | None`:
  `session = await Session.get_or_none(id=session_id)`;
  if `None` or expired, return `None`;
  else `max(0, int((expires_at - now()).total_seconds()))`.

`SessionRefreshMiddleware` works unchanged: it reads `remaining_ttl`, and on a
near-expiry session it calls `create_session` then `expire_session(sid,
SESSION_ROTATE_GRACE_SECONDS)`.

### `app/services/rate_limit.py` (rewritten, same `RateLimiter` protocol)

- `PostgresFixedWindowLimiter.check(key, *, limit, window_s) ->
  RateLimitResult`:
  1. `limit <= 0` -> return `(True, 0)` (unlimited; no DB write).
  2. Compute `now_us` and `window_start = now_us - (now_us % window_s_us)`.
  3. Prune: `DELETE FROM rate_limit_counters WHERE key = ? AND
     window_start < ?` (drops dead windows).
  4. Atomic upsert and increment, returning the new count:
     ```sql
     INSERT INTO rate_limit_counters (key, window_start, count)
     VALUES (?, ?, 1)
     ON CONFLICT (key, window_start)
     DO UPDATE SET count = count + 1
     RETURNING count
     ```
  5. If returned `count <= limit` -> `(True, 0)`. Else -> `(False,
     retry_after)` where `retry_after = ceil((window_start + window_s_us -
     now_us) / 1_000_000)`, floored to a minimum of 1.
  6. On any DB exception -> fail-closed: return `(False, 1)`, log once on the
     healthy -> failing transition via a `LimiterHealth` guard. Recovery (the
     next successful query) logs the count of degraded requests.

`INSERT ... ON CONFLICT ... RETURNING` is valid on both Postgres and SQLite
(3.35+), so the same raw SQL runs in tests with no mock.

`build_limiter()` returns `PostgresFixedWindowLimiter()` always (Postgres is the
only backend). The `url` parameter is removed; there is no branching.

The over-increment on a denied request is harmless: the counter grows for one
window, then is pruned. The exact limit is still enforced: the
`count <= limit` check admits exactly `limit` requests per window.

## Error handling and edge cases

### Sessions

- An expired session read returns `None` and deletes the row (lazy delete). The
  callers (auth deps, WS auth, middleware) already treat `None` as "no session"
  -> 401 or redirect. No new error path.
- `expire_session` on a missing sid affects 0 rows silently. Same behavior as
  Redis (`EXPIRE` on a missing key is a no-op).
- Session table growth: `expires_at` is indexed. The only unbounded growth is
  expired rows that are never re-read (a user closes the tab). Lazy delete
  catches reads. A periodic reaper can be added later if the table grows:
  `# withinlazy: lazy-delete-only; add a periodic DELETE ... WHERE
  expires_at <= now() reaper if the sessions table grows past a ceiling`.

### Rate limit

- Postgres unreachable or query error -> `(False, 1)` fail-closed, logged once
  on healthy -> failing. `_acquire` sleeps `max(retry_after, 0.02)` and retries
  -> backpressure, no crash, no new error kind.
- Fixed window allows up to ~2x the limit at a window boundary (a burst
  straddling two windows). Accepted: this throttle protects the provider, not a
  hard SLO.
- Unlimited providers (`limit <= 0`) short-circuit before any DB write. Zero
  writes, matching today's behavior.

### Config removal

- `REDIS_URL` and `REDIS_SOCKET_TIMEOUT_MS` are deleted from `Settings`. Any
  env var still set in `.env` is ignored (pydantic-settings ignores unknowns by
  default). No startup failure.
- `redis` is removed from `pyproject.toml` dependencies. All `redis.asyncio`
  import sites are deleted with the removed code.
- `docker-compose.yaml`: delete the `redis` service block, its volume, the
  backend `REDIS_URL` env, and the `depends_on: redis` entry.
- The agent-proxy bypass regex in `app/auth/dependencies.py` is unrelated to
  Redis and is not touched.

## Testing

Tests follow the existing pattern: pytest + async, in-memory SQLite schema
generated by Tortoise from the registered models. No new framework.

### Sessions — `tests/services/test_auth_session.py` (rewritten)

The current tests target `_InProcessSessions` internals; those classes are
deleted, so the tests move to the module-level functions against the DB. Same
intent, new backing.

- Set + get + delete roundtrip.
- Expired session read returns `None` and deletes the row (assert the row is
  gone after the read).
- `expire_session` shortens TTL; `remaining_ttl` reflects it; the session still
  resolves within the grace window.
- `remaining_ttl` returns `None` for a missing or expired session.
- `delete_session` and `expire_session` on a missing sid are no-ops (no raise).

### Rate limit — `tests/test_rate_limit.py` (new)

Deleted tests: `tests/test_redis_rate_limit.py`,
`tests/test_redis_health.py`, `tests/test_fail_open_observability.py`,
`tests/test_rate_limit_degrade.py`, `tests/test_limiter_factory.py`. Their
intent (observability on outage, the factory returns the limiter) is
re-expressed against the Postgres limiter in `tests/test_rate_limit.py`.

- Under-limit increments the counter, returns `(True, 0)`.
- At-limit returns `(False, retry_after)` with `1 <= retry_after <= window_s`
  (the wait until the current window ends).
- The next window resets the counter (prune + new `window_start`), allows
  again.
- `limit <= 0` short-circuits, no DB write (assert no row created).
- Fail-closed: force a DB error (monkeypatch the query to raise) -> returns
  `(False, 1)`, logs once on the first failure; a second failure does not
  re-log; recovery logs the degraded count.
- Fixed-window boundary behavior is documented with one assertion: a burst
  across two windows admits up to ~2x the limit.

### Surface and regression

- `tests/test_surface_parity.py`: no route change, so it stays green as-is.
- The full backend suite must pass after the swap (current baseline: 852 pass /
  6 skip).

## TDD order

1. `RateLimitCounter` model + `PostgresFixedWindowLimiter` (the trickier SQL
   first).
2. `Session` model + the rewritten `auth_session` service functions.
3. Wire-up and config removal (`build_limiter`, `config.py`, `pyproject.toml`,
   `docker-compose.yaml`).
4. Delete the Redis code and the Redis tests.

Each step: failing test -> minimal code to pass -> confirm pass -> refactor. No
exceptions.
