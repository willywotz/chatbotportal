# Context — running changelog

## 2026-08-17 — Replace Redis with Postgres

Branch: `refactor/redis-to-postgres`.

### What changed
- Redis is removed. Postgres is now the only backend datastore for the two
  things Redis did: auth session storage and LLM-provider rate limiting.
- Auth sessions: new `Session` model (`backend/app/models/session.py`,
  table `sessions`). The session id is `generate_uuid7().hex`. Expired
  sessions are deleted lazily on read (`resolve_session`). The five public
  functions in `backend/app/services/auth_session.py` keep the same names
  and signatures, so the auth router, the WebSocket auth, and the
  session-refresh middleware do not change.
- Rate limiting: new `RateLimitCounter` model
  (`backend/app/models/rate_limit_counter.py`, table `rate_limit_counters`)
  and `PostgresFixedWindowLimiter` (`backend/app/services/rate_limit.py`).
  The limiter uses a fixed-window counter with a `get_or_create` increment.
  It is fail-closed: a datastore error returns `(allowed=False, retry_after=1)`,
  and the LLM client retry loop turns this into backpressure. The
  `RateLimiter` protocol and `build_limiter()` stay, so `llm/client.py` does
  not change.
- Redis removal: the `redis` service block, the `REDIS_URL` env, and the
  `depends_on` entry are deleted from `docker-compose.yaml`. The `redis`
  dependency is removed from `backend/pyproject.toml` and `backend/uv.lock`.
  The redis service container and the `TEST_REDIS_URL` env are removed from
  `.github/workflows/test.yml`. `REDIS_URL` and `REDIS_SOCKET_TIMEOUT_MS` are
  removed from `backend/app/config.py`.

### Verification
- Full backend suite: 845 passed, 2 skipped.
- Surface parity: 4 passed (no route changed).
- Zero Redis references in `backend/app`, `docker-compose.yaml`, and
  `.github/workflows/test.yml`.
- `docker compose config` is valid.

### Known limits (lazy)
- The rate-limit counter is a read-modify-write, not an atomic upsert.
  Concurrent workers can lose increments. This is acceptable: the counter is
  approximate backpressure, not a hard limit. Upgrade path: a raw
  `ON CONFLICT` upsert (see the `withinlazy:` comment in `rate_limit.py`).
- Expired sessions are deleted only when read. A periodic reaper can be added
  if the `sessions` table grows (see the `withinlazy:` comment in
  `auth_session.py`).
- Fixed-window rate limiting allows up to ~2x the limit at a window boundary.

### Note for deploy
- No Aerich migration was generated. The test database uses
  `Tortoise.generate_schemas()`. For a live Postgres deploy, the `sessions`
  and `rate_limit_counters` tables must be created (by a migration or by
  schema generation) before the backend starts.
- The `agent-proxy` job in `.github/workflows/test.yml` is a pre-existing
  dangling job (the `agent-proxy/` directory was deleted in a prior task).
  It is not part of this change. It will fail in CI until it is removed.
