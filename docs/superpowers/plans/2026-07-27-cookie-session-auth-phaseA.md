# Cookie Session Auth — Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace browser JWT-bearer-in-localStorage auth with an opaque HttpOnly session cookie backed by Redis, keep API-key as a separate machine channel, remove JWT entirely, and migrate the OpenAI-compatible surfaces off auto-ephemeral users.

**Architecture:** A Redis-backed session store (`session:<id> → user_id`, TTL) issued as an `HttpOnly; Secure; SameSite=Lax` cookie on login. Both auth chokepoints (`get_current_user*` and the global `enforce_role_allowlist`/`_resolve_role`) resolve the caller from the `Authorization` header (API-key) **or** the session cookie. A middleware re-rotates near-expiry sessions. Frontend goes fully header-free (`withCredentials`).

**Tech Stack:** Python 3.12, FastAPI/Starlette, Tortoise ORM, `redis>=5.0.0` (`redis.asyncio`), pytest; frontend React + TypeScript, axios, Vitest + MSW.

## Global Constraints

- TDD mandatory: failing test → confirm fail → minimal code → confirm pass → commit. One behavior per test.
- Google style (Python/TS); clean minimal code; imports sorted by path; American English.
- **`rtk pytest` cannot spawn in this environment** — run backend tests with `.venv/bin/pytest <path>` from `backend/`. Frontend: `rtk vitest run <path>` from `frontend/` (works), else `./node_modules/.bin/vitest run`.
- Orchestrator (Main) owns git/commits/context.md; builders do NOT commit.
- Session cookie: `HttpOnly; Secure=<AUTH_COOKIE_SECURE>; SameSite=Lax; Path=/; Max-Age=SESSION_TTL_MINUTES*60`. Cookie name `settings.SESSION_COOKIE_NAME` (default `"session_id"`).
- CSRF: SameSite=Lax only (same-origin app). No CSRF token.
- **JWT is removed** — no `create_access_token`/`decode_access_token`/`JWT_*` after Task 8.
- Preserve the optional-auth asymmetry: a present-but-invalid **API key** → 401; a missing/expired **session cookie** → anonymous.
- Redis via `settings.REDIS_URL`; empty → in-process fallback (dev). Reuse the degradation spirit of `app/services/rate_limit.py`.
- Spec: `docs/superpowers/specs/2026-07-27-cookie-session-auth-phaseA-design.md`.
- Branch: `feat/auth-cookie-core` (already created off `dev`).

---

## File Structure

**Create:**
- `backend/app/services/auth_session.py` — Redis/in-process session store.
- `backend/app/middleware/session_refresh.py` — sliding-refresh middleware.
- `backend/tests/services/test_auth_session.py`
- `backend/tests/auth/test_session_cookie_auth.py` — resolution (cookie/api-key) at both chokepoints.
- `backend/tests/routers/test_auth_login_logout.py`
- `backend/tests/middleware/test_session_refresh.py`

**Modify:**
- `backend/app/config.py` — add session settings (Task 1); remove JWT settings (Task 8).
- `backend/app/auth/dependencies.py` — cookie/api-key resolution (Task 3).
- `backend/app/routers/auth.py` — login sets cookie, `/auth/logout` (Task 4).
- `backend/app/main.py` — register middleware (Task 5); CORS credentials (Task 7).
- `backend/app/routers/responses.py`, `backend/app/routers/openai_conversations.py`, `backend/app/services/openai/identity.py` — required auth + drop ephemeral (Task 6).
- `backend/app/auth/security.py` — remove JWT (Task 8).
- `backend/tests/test_surface_parity.py` — add `/auth/logout` (Task 6 or 9).
- Frontend: `shared/lib/apiClient.ts`, `features/auth/useAuth.tsx`, `features/auth/LoginPage.tsx`, `features/chat/chatApi.ts`, `features/agencies/useAgencies.ts` (Tasks 9–10).

**Dependency order:** 1 → 2 → 3 → (4, 5, 6 parallelizable after 3) → 7 (CORS) → 8 (JWT removal, after 3/4/6) → 9 → 10 → 11.

---

## Task 1: Session settings

**Files:** Modify `backend/app/config.py`; Test: `backend/tests/test_config_session.py`

**Interfaces — Produces:** `settings.SESSION_COOKIE_NAME: str`, `AUTH_COOKIE_SECURE: bool`, `SESSION_TTL_MINUTES: int`, `SESSION_REFRESH_BELOW_MINUTES: int`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_config_session.py
from app.config import settings


def test_session_settings_defaults():
    assert settings.SESSION_COOKIE_NAME == "session_id"
    assert settings.AUTH_COOKIE_SECURE is True
    assert settings.SESSION_TTL_MINUTES == 60 * 24 * 7
    assert settings.SESSION_REFRESH_BELOW_MINUTES == 60 * 24 * 3
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError`). `cd backend && .venv/bin/pytest tests/test_config_session.py -v`

- [ ] **Step 3: Implement** — in `backend/app/config.py`, in the `# ── Chat`/auth area near the other settings, add:

```python
    # ── Session cookie auth ──────────────────────────────────────────────────
    SESSION_COOKIE_NAME: str = "session_id"
    AUTH_COOKIE_SECURE: bool = True
    SESSION_TTL_MINUTES: int = 60 * 24 * 7          # 7 days
    SESSION_REFRESH_BELOW_MINUTES: int = 60 * 24 * 3  # re-rotate below ~half TTL
```

- [ ] **Step 4: Run — expect PASS**
- [ ] **Step 5: Commit** — `feat: add session-cookie auth settings`

---

## Task 2: Redis session store

**Files:** Create `backend/app/services/auth_session.py`; Test: `backend/tests/services/test_auth_session.py`

**Interfaces:**
- Consumes: `settings.REDIS_URL`, `settings.SESSION_TTL_MINUTES`.
- Produces:
  - `async create_session(user_id: str) -> str`
  - `async resolve_session(session_id: str) -> str | None`
  - `async delete_session(session_id: str) -> None`
  - `async remaining_ttl(session_id: str) -> int | None`
  - `class _InProcessSessions` with `now_fn` injection (for unit tests).

- [ ] **Step 1: Failing test**

```python
# backend/tests/services/test_auth_session.py
import pytest

from app.services.auth_session import (
    _InProcessSessions, create_session, delete_session, remaining_ttl, resolve_session,
)


def test_inprocess_set_get_delete_and_expiry():
    clock = {"t": 1000.0}
    store = _InProcessSessions(now_fn=lambda: clock["t"])
    store.set("s1", "u1", ttl=100)
    assert store.get("s1") == "u1"
    assert 0 < store.ttl("s1") <= 100
    clock["t"] += 101            # advance past ttl
    assert store.get("s1") is None
    assert store.ttl("s1") is None
    store.set("s2", "u2", ttl=100)
    store.delete("s2")
    assert store.get("s2") is None


@pytest.mark.asyncio
async def test_module_roundtrip_uses_inprocess_when_no_redis(monkeypatch):
    # REDIS_URL is empty in tests -> in-process backend.
    sid = await create_session("user-123")
    assert await resolve_session(sid) == "user-123"
    assert (await remaining_ttl(sid)) > 0
    await delete_session(sid)
    assert await resolve_session(sid) is None
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`). `cd backend && .venv/bin/pytest tests/services/test_auth_session.py -v`

- [ ] **Step 3: Implement**

```python
# backend/app/services/auth_session.py
"""Opaque server-side session store for browser auth.

Sessions map an opaque id -> user_id with a TTL. Redis-backed when REDIS_URL is
set (shared across workers); an in-process fallback keeps single-worker dev
working without Redis, mirroring app/services/rate_limit.py's degradation.
"""
import time
import uuid

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.config import settings

_PREFIX = "session:"


class _InProcessSessions:
    """Per-process fallback store; monotonic-clock TTL. Injectable clock for tests."""

    def __init__(self, now_fn=time.monotonic):
        self._now = now_fn
        self._store: dict[str, tuple[str, float]] = {}

    def set(self, sid: str, user_id: str, *, ttl: int) -> None:
        self._store[sid] = (user_id, self._now() + ttl)

    def get(self, sid: str) -> str | None:
        item = self._store.get(sid)
        if item is None:
            return None
        user_id, expires_at = item
        if expires_at <= self._now():
            self._store.pop(sid, None)
            return None
        return user_id

    def delete(self, sid: str) -> None:
        self._store.pop(sid, None)

    def ttl(self, sid: str) -> int | None:
        item = self._store.get(sid)
        if item is None:
            return None
        remaining = int(item[1] - self._now())
        return remaining if remaining > 0 else None


class _RedisSessions:
    def __init__(self, client):
        self._c = client

    async def set(self, sid: str, user_id: str, *, ttl: int) -> None:
        await self._c.set(_PREFIX + sid, user_id, ex=ttl)

    async def get(self, sid: str) -> str | None:
        return await self._c.get(_PREFIX + sid)

    async def delete(self, sid: str) -> None:
        await self._c.delete(_PREFIX + sid)

    async def ttl(self, sid: str) -> int | None:
        t = await self._c.ttl(_PREFIX + sid)  # -2 no key, -1 no expiry
        return t if t is not None and t >= 0 else None


_inprocess = _InProcessSessions()
_redis: _RedisSessions | None = None


def _redis_backend() -> _RedisSessions | None:
    global _redis
    if not settings.REDIS_URL:
        return None
    if _redis is None:
        _redis = _RedisSessions(aioredis.from_url(settings.REDIS_URL, decode_responses=True))
    return _redis


def _ttl_seconds() -> int:
    return settings.SESSION_TTL_MINUTES * 60


async def create_session(user_id: str) -> str:
    sid = uuid.uuid4().hex
    ttl = _ttl_seconds()
    backend = _redis_backend()
    if backend is not None:
        try:
            await backend.set(sid, user_id, ttl=ttl)
            return sid
        except (RedisError, OSError):
            pass  # degrade to in-process
    _inprocess.set(sid, user_id, ttl=ttl)
    return sid


async def resolve_session(session_id: str) -> str | None:
    backend = _redis_backend()
    if backend is not None:
        try:
            return await backend.get(session_id)
        except (RedisError, OSError):
            pass
    return _inprocess.get(session_id)


async def delete_session(session_id: str) -> None:
    backend = _redis_backend()
    if backend is not None:
        try:
            await backend.delete(session_id)
            return
        except (RedisError, OSError):
            pass
    _inprocess.delete(session_id)


async def remaining_ttl(session_id: str) -> int | None:
    backend = _redis_backend()
    if backend is not None:
        try:
            return await backend.ttl(session_id)
        except (RedisError, OSError):
            pass
    return _inprocess.ttl(session_id)
```

- [ ] **Step 4: Run — expect PASS** (2 tests)
- [ ] **Step 5: Commit** — `feat: Redis-backed opaque session store with in-process fallback`

---

## Task 3: Cookie/API-key resolution in dependencies (crux)

**Files:** Modify `backend/app/auth/dependencies.py`; Test: `backend/tests/auth/test_session_cookie_auth.py`

**Interfaces:**
- Consumes: `resolve_session` (Task 2), `settings.SESSION_COOKIE_NAME`, `API_KEY_PREFIX`, `hash_api_key` (still in `security.py`).
- Produces (signature changes): `get_current_user(request: Request)`, `get_current_user_optional(request: Request)`, `enforce_role_allowlist(request: Request)` all now take only `Request`. Internal: `_header_api_key(request)`, `_resolve_api_key(token)`, `_resolve_session_user(sid)`, `_resolve_role(request)`.
- **The JWT branch is removed** from `_resolve_token`/`_resolve_role` here.

- [ ] **Step 1: Failing test**

```python
# backend/tests/auth/test_session_cookie_auth.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import (
    enforce_role_allowlist, get_current_user, get_current_user_optional,
)
from app.config import settings
from app.models.user import User


def _app():
    app = FastAPI(dependencies=[Depends(enforce_role_allowlist)])

    @app.get("/api/v1/who")
    async def who(user=Depends(get_current_user)):
        return {"id": str(user.id), "role": user.role}

    @app.get("/api/v1/maybe")
    async def maybe(user=Depends(get_current_user_optional)):
        return {"anon": user is None}

    return app


@pytest.mark.asyncio
async def test_session_cookie_authenticates(db):
    user = await User.create(email="a@b.co", hashed_password="x", role="admin", is_active=True)
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=str(user.id))):
        client = TestClient(_app())
        r = client.get("/api/v1/who", cookies={settings.SESSION_COOKIE_NAME: "sid-1"})
    assert r.status_code == 200 and r.json()["id"] == str(user.id)


@pytest.mark.asyncio
async def test_no_credential_is_anonymous_on_optional(db):
    client = TestClient(_app())
    r = client.get("/api/v1/maybe")
    assert r.json() == {"anon": True}


@pytest.mark.asyncio
async def test_bad_api_key_401s_but_bad_session_is_anon(db):
    client = TestClient(_app())
    # invalid API key -> 401 (deliberate credential)
    r1 = client.get("/api/v1/maybe", headers={"Authorization": "Bearer tcg_bogus"})
    assert r1.status_code == 401
    # unknown session cookie -> anonymous
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=None)):
        r2 = client.get("/api/v1/maybe", cookies={settings.SESSION_COOKIE_NAME: "dead"})
    assert r2.status_code == 200 and r2.json() == {"anon": True}
```

- [ ] **Step 2: Run — expect FAIL.** `cd backend && .venv/bin/pytest tests/auth/test_session_cookie_auth.py -v`

- [ ] **Step 3: Implement** — rewrite the resolution core of `dependencies.py`. Replace the `HTTPBearer` deps and `_resolve_token`/`_resolve_role`/`get_current_user*`/`enforce_role_allowlist` with request-based versions. Keep the allowlist predicate functions (`_is_public_get`, `_is_shared_write`, `_is_allowed_for_*`, regexes, `_STAFF_GET_EXACT`) unchanged. New auth core:

```python
from fastapi import Depends, HTTPException, Request, status

from app.auth.security import API_KEY_PREFIX, hash_api_key
from app.config import settings
from app.models.user import User, UserAPIKey
from app.services.auth_session import resolve_session
from app.services.usage_context import current_api_key_id, current_user_id
from app.utils import now

_invalid_credentials = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _header_api_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else None


async def _resolve_api_key(token: str) -> User | None:
    """API-key path only (JWT is gone). Stamps last_used + usage context."""
    if not token.startswith(API_KEY_PREFIX):
        return None
    api_key = await UserAPIKey.filter(key_hash=hash_api_key(token)).first()
    if api_key is None or not api_key.is_usable():
        return None
    user = await User.filter(id=api_key.user_id, is_active=True).first()
    if user is None:
        return None
    api_key.last_used_at = now()
    await api_key.save(update_fields=["last_used_at"])
    current_user_id.set(user.id)
    current_api_key_id.set(api_key.id)
    return user


async def _resolve_session_user(session_id: str) -> User | None:
    user_id = await resolve_session(session_id)
    if not user_id:
        return None
    user = await User.filter(id=user_id, is_active=True).first()
    if user is not None:
        current_user_id.set(user.id)
    return user


async def get_current_user_optional(request: Request) -> User | None:
    key = _header_api_key(request)
    if key is not None:
        user = await _resolve_api_key(key)
        if user is None:            # deliberate API key that fails must 401
            raise _invalid_credentials
        return user
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        return await _resolve_session_user(sid)  # bad session -> None (anonymous)
    return None


async def get_current_user(request: Request) -> User:
    key = _header_api_key(request)
    user = await _resolve_api_key(key) if key is not None else None
    if user is None:
        sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
        if sid:
            user = await _resolve_session_user(sid)
    if user is None:
        raise _invalid_credentials
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user


async def _resolve_role(request: Request) -> str | None:
    """Role only, no side effects (no last_used stamp / rate charge)."""
    key = _header_api_key(request)
    if key is not None:
        if not key.startswith(API_KEY_PREFIX):
            return None
        api_key = await UserAPIKey.filter(key_hash=hash_api_key(key)).first()
        if api_key is None or not api_key.is_usable():
            return None
        user = await User.filter(id=api_key.user_id, is_active=True).first()
        return user.role if user else None
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        user_id = await resolve_session(sid)
        if user_id:
            user = await User.filter(id=user_id, is_active=True).first()
            return user.role if user else None
    return None


async def enforce_role_allowlist(request: Request) -> None:
    if _is_public_get(request.method, request.url.path):
        return
    role = await _resolve_role(request)
    if role is None or role == "admin":   # anonymous/invalid pass; admin per-endpoint
        return
    check = _ROLE_ALLOWLIST.get(role, _is_allowed_for_basic_user)
    if not check(request.method, request.url.path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This role does not have access to this resource")
```

Remove `from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer`, the `_bearer`/`_bearer_optional` globals, `from jose import JWTError`, `decode_access_token` import, and the old `_resolve_token`. (Consumers that imported `_resolve_token` — the responses WS `_ws_user` and chat `bearer_user` — still import `_resolve_token`; keep a thin `_resolve_token = _resolve_api_key` alias export OR update those callers. See note below.)

> **Cross-file note for the implementer:** `app/routers/responses.py::_ws_user` and `app/services/chat/ws.py::bearer_user` call `await _resolve_token(token)`. Since browsers can't set WS headers, these WS paths stay bearer/API-key-only in Phase A. Keep them working by exporting `_resolve_token = _resolve_api_key` (module-level alias) so their header tokens resolve as API keys. Add a one-line test that `dependencies._resolve_token is dependencies._resolve_api_key`.

- [ ] **Step 4: Run — expect PASS.** Then run the auth-adjacent suites to catch fallout: `.venv/bin/pytest tests/auth tests/test_basic_user_allowlist.py tests/test_staff_allowlist.py tests/routers/test_chat_ws.py -q`. Fix any test that constructed `get_current_user` with `credentials=` (now `request`).

- [ ] **Step 5: Commit** — `feat: resolve caller from session cookie or API-key (drop JWT branch)`

---

## Task 4: Login sets session cookie + logout endpoint

**Files:** Modify `backend/app/routers/auth.py`; Test: `backend/tests/routers/test_auth_login_logout.py`

**Interfaces:**
- Consumes: `create_session`, `delete_session` (Task 2); `settings` cookie fields.
- Produces: `POST /auth/login` sets the session cookie and returns `{ "user": {…} }` (no `access_token`); `POST /auth/logout` deletes the session + clears the cookie.

- [ ] **Step 1: Failing test**

```python
# backend/tests/routers/test_auth_login_logout.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.models.user import User
from app.routers import auth as auth_router
from app.services.user import hash_new_password


def _app():
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_login_sets_cookie_and_omits_token(db):
    await User.create(email="a@b.co", hashed_password=hash_new_password("pw12345"),
                      role="admin", is_active=True)
    client = TestClient(_app())
    r = client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "pw12345"})
    assert r.status_code == 200
    assert "access_token" not in r.json()
    assert r.json()["user"]["email"] == "a@b.co"
    set_cookie = r.headers["set-cookie"]
    assert settings.SESSION_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie and "SameSite=Lax" in set_cookie


@pytest.mark.asyncio
async def test_logout_clears_cookie(db):
    await User.create(email="a@b.co", hashed_password=hash_new_password("pw12345"),
                      role="admin", is_active=True)
    client = TestClient(_app())
    client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "pw12345"})
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    # Deletion is a Set-Cookie with an expiry in the past / Max-Age=0.
    assert settings.SESSION_COOKIE_NAME in r.headers.get("set-cookie", "")
```

- [ ] **Step 2: Run — expect FAIL.** `cd backend && .venv/bin/pytest tests/routers/test_auth_login_logout.py -v`

- [ ] **Step 3: Implement** — in `auth.py`:
- Replace the `create_access_token` import with `from app.services.auth_session import create_session, delete_session`.
- Rewrite `login` to take `response: Response` and set the cookie:

```python
@router.post("/login", summary="Sign in and start a session")
async def login(body: LoginRequest, response: Response) -> dict:
    user = await User.filter(email=body.email, is_active=True).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    session_id = await create_session(str(user.id))
    response.set_cookie(
        settings.SESSION_COOKIE_NAME, session_id,
        httponly=True, secure=settings.AUTH_COOKIE_SECURE, samesite="lax",
        max_age=settings.SESSION_TTL_MINUTES * 60, path="/",
    )
    return {"user": _user_dict(user)}


@router.post("/logout", summary="End the current session")
async def logout(request: Request, response: Response) -> dict:
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        await delete_session(sid)
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    return {"ok": True}
```

Add imports `from fastapi import Request, Response` and `from app.config import settings`.

- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** — `feat: login issues session cookie; add POST /auth/logout`

---

## Task 5: Sliding session-refresh middleware

**Files:** Create `backend/app/middleware/session_refresh.py`; Modify `backend/app/main.py`; Test: `backend/tests/middleware/test_session_refresh.py`

**Interfaces:**
- Consumes: `create_session`, `delete_session`, `remaining_ttl` (Task 2); `settings`.
- Produces: `SessionRefreshMiddleware` (Starlette `BaseHTTPMiddleware`).

- [ ] **Step 1: Failing test**

```python
# backend/tests/middleware/test_session_refresh.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.middleware.session_refresh import SessionRefreshMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(SessionRefreshMiddleware)

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    return app


def test_near_expiry_session_is_rotated():
    with patch("app.middleware.session_refresh.remaining_ttl", new=AsyncMock(return_value=60)), \
         patch("app.middleware.session_refresh.resolve_session", new=AsyncMock(return_value="u1")), \
         patch("app.middleware.session_refresh.create_session", new=AsyncMock(return_value="new-sid")), \
         patch("app.middleware.session_refresh.delete_session", new=AsyncMock()) as deleted:
        client = TestClient(_app())
        r = client.get("/api/v1/ping", cookies={settings.SESSION_COOKIE_NAME: "old-sid"})
    assert "new-sid" in r.headers.get("set-cookie", "")
    deleted.assert_awaited_once_with("old-sid")


def test_fresh_session_not_rotated():
    huge = settings.SESSION_TTL_MINUTES * 60
    with patch("app.middleware.session_refresh.remaining_ttl", new=AsyncMock(return_value=huge)), \
         patch("app.middleware.session_refresh.create_session", new=AsyncMock()) as created:
        client = TestClient(_app())
        r = client.get("/api/v1/ping", cookies={settings.SESSION_COOKIE_NAME: "old-sid"})
    created.assert_not_awaited()
    assert "set-cookie" not in {k.lower() for k in r.headers}


def test_no_cookie_no_rotation():
    with patch("app.middleware.session_refresh.remaining_ttl", new=AsyncMock()) as ttl:
        client = TestClient(_app())
        client.get("/api/v1/ping")
    ttl.assert_not_awaited()
```

- [ ] **Step 2: Run — expect FAIL.** `cd backend && .venv/bin/pytest tests/middleware/test_session_refresh.py -v`

- [ ] **Step 3: Implement**

```python
# backend/app/middleware/session_refresh.py
"""Re-rotate a near-expiry session cookie on any authenticated request.

Keeps an active browser's session sliding forward; idle sessions still expire.
Only session-cookie requests are touched — API-key/anonymous requests are not.
"""
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.services.auth_session import (
    create_session, delete_session, remaining_ttl, resolve_session,
)


class SessionRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
        response = await call_next(request)
        if not sid:
            return response
        ttl = await remaining_ttl(sid)
        if ttl is None or ttl >= settings.SESSION_REFRESH_BELOW_MINUTES * 60:
            return response
        user_id = await resolve_session(sid)
        if not user_id:
            return response
        new_sid = await create_session(user_id)
        await delete_session(sid)
        response.set_cookie(
            settings.SESSION_COOKIE_NAME, new_sid,
            httponly=True, secure=settings.AUTH_COOKIE_SECURE, samesite="lax",
            max_age=settings.SESSION_TTL_MINUTES * 60, path="/",
        )
        return response
```

- [ ] **Step 4: Wire it** — in `backend/app/main.py`, add `app.add_middleware(SessionRefreshMiddleware)` (import at top). Order note: add it so it wraps requests alongside CORS; placement relative to CORS does not matter for cookie writes.

- [ ] **Step 5: Run — expect PASS** (3 tests) + `.venv/bin/python -c "import app.main"`.
- [ ] **Step 6: Commit** — `feat: sliding session-refresh middleware (re-rotate near expiry)`

---

## Task 6: Require auth on OpenAI surfaces; remove ephemeral users

**Files:** Modify `backend/app/routers/responses.py`, `backend/app/routers/openai_conversations.py`, `backend/app/services/openai/identity.py`; Test: `backend/tests/routers/test_openai_requires_auth.py`

**Interfaces:**
- Consumes: `get_current_user` (Task 3).
- Produces: `/responses` + `/conversations` require an authenticated caller (401 anonymous); `owner_or_ephemeral` and the `X-Portal-Session` header are removed; `owns` is kept.

- [ ] **Step 1: Failing test**

```python
# backend/tests/routers/test_openai_requires_auth.py
import pytest
from fastapi.testclient import TestClient

from tests.routers.test_responses_http import _client_app  # existing helper builds the app


def test_responses_anonymous_is_401(db):
    with TestClient(_client_app()) as client:
        r = client.post("/api/v1/responses", json={"model": "onechat", "input": "hi"})
    assert r.status_code == 401


def test_conversations_anonymous_is_401(db):
    with TestClient(_client_app()) as client:
        r = client.post("/api/v1/conversations", json={})
    assert r.status_code == 401
```

(If `_client_app` doesn't mount `openai_conversations`, build a small local app that includes both routers with the global `enforce_role_allowlist` dependency.)

- [ ] **Step 2: Run — expect FAIL** (currently 200 via ephemeral user). `cd backend && .venv/bin/pytest tests/routers/test_openai_requires_auth.py -v`

- [ ] **Step 3: Implement**
- `responses.py`: change `user: User | None = Depends(get_current_user_optional)` → `user: User = Depends(get_current_user)` on `create_response` (and the other `get_current_user_optional` sites at lines ~160/165/182). Remove the `owner_or_ephemeral` call and the `session_token`/`X-Portal-Session` header logic (the `owner, session_token = await owner_or_ephemeral(user)` block and every `resp.headers["X-Portal-Session"] = session_token`). Use `user` directly as the owner.
- `openai_conversations.py`: change all `get_current_user_optional` → `get_current_user`; replace `owner, token = await owner_or_ephemeral(user)` with `owner = user`; drop the `token`/header usage; keep `owns`.
- `identity.py`: delete `owner_or_ephemeral` (and any now-unused imports/`create_access_token` use). Keep `owns`.
- Grep `X-Portal-Session` and `owner_or_ephemeral` across `app/` to confirm zero remaining references.

- [ ] **Step 4: Run** — the new test PASSES; then re-run the responses/conversations suites and fix tests that assumed anonymous/ephemeral access (they must now pass an API key or session). `.venv/bin/pytest tests/routers/test_responses_http.py tests/routers/test_responses_ws_route.py -q` (update as needed).

- [ ] **Step 5: Commit** — `feat: require auth on /responses + /conversations; remove ephemeral users`

---

## Task 7: CORS credentials + explicit origins

**Files:** Modify `backend/app/main.py`, `backend/app/config.py`; Test: `backend/tests/test_cors_credentials.py`

**Interfaces:** Produces CORS with `allow_credentials=True` and a non-wildcard default origin list.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_cors_credentials.py
from fastapi.testclient import TestClient

from app.main import app


def test_cors_allows_credentials_for_configured_origin():
    client = TestClient(app)
    r = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:5173",
                 "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-credentials") == "true"
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
```

- [ ] **Step 2: Run — expect FAIL.** `cd backend && .venv/bin/pytest tests/test_cors_credentials.py -v`

- [ ] **Step 3: Implement**
- `config.py`: change `CORS_ORIGINS` default from `["*"]` to `["http://localhost:5173", "http://localhost:8080"]` (dev origins; prod overrides via env, already in `.env.prod.example`).
- `main.py`: add `allow_credentials=True` to the `CORSMiddleware` call. (Wildcard + credentials is invalid, so this must accompany the non-wildcard default.)

- [ ] **Step 4: Run — expect PASS.** Then check no existing test asserted wildcard CORS; update if present.
- [ ] **Step 5: Commit** — `feat: enable credentialed CORS with explicit origins`

---

## Task 8: Remove JWT entirely

**Files:** Modify `backend/app/auth/security.py`, `backend/app/config.py`; Test: rewrite/delete JWT tests.

**Interfaces:** Removes `create_access_token`, `decode_access_token`, `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`, and the JWT prod-secret assertion. API-key + password hashing remain.

- [ ] **Step 1: Confirm no runtime users remain** — `cd backend && rtk grep -rn "create_access_token\|decode_access_token\|JWT_SECRET\|JWT_ALGORITHM\|JWT_EXPIRE_MINUTES" app`. Expected after Tasks 3/4/6: no references in `app/` except `security.py`/`config.py` definitions. If any remain (e.g. a stray import), that's a signal an earlier task missed a spot — fix it here.

- [ ] **Step 2: Write/adjust the failing test**

```python
# backend/tests/test_jwt_removed.py
def test_jwt_helpers_are_gone():
    import app.auth.security as sec
    assert not hasattr(sec, "create_access_token")
    assert not hasattr(sec, "decode_access_token")

def test_jwt_settings_removed():
    from app.config import settings
    for name in ("JWT_SECRET", "JWT_ALGORITHM", "JWT_EXPIRE_MINUTES"):
        assert not hasattr(settings, name)
```

- [ ] **Step 3: Run — expect FAIL.** `.venv/bin/pytest tests/test_jwt_removed.py -v`

- [ ] **Step 4: Implement**
- `security.py`: delete `create_access_token`, `decode_access_token`, and the `from jose import JWTError, jwt` import + the JWT section header. Keep password + API-key helpers.
- `config.py`: delete `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`, and the `assert_production_secrets` JWT check (or the whole function if it only checked JWT — verify `config.py:148-152`).
- Delete/rewrite obsolete JWT tests: `tests/test_config_onechat_base.py` and any auth test asserting JWT behavior; the existing `tests/test_*` that build tokens via `create_access_token` must switch to session cookies or API keys (grep `create_access_token` in `tests/` and fix each).

- [ ] **Step 5: Run** — `.venv/bin/pytest tests/test_jwt_removed.py -v` PASS, then the full suite `.venv/bin/pytest -q` green.
- [ ] **Step 6: Commit** — `refactor: remove JWT auth (sessions + API-keys only)`

---

## Task 9: Frontend — cookie-based auth context

**Files:** Modify `frontend/src/features/auth/useAuth.tsx`, `frontend/src/features/auth/LoginPage.tsx`; Test: `useAuth.test.tsx`, `LoginPage.test.tsx` (update existing).

**Interfaces — Produces:** `setAuth(user: AuthUser)` (no token arg); mount-restore always calls `/auth/me`; `signOut` calls `POST /auth/logout`.

- [ ] **Step 1: Update the failing tests** — in `useAuth.test.tsx`: assert that on mount the provider calls `GET /api/v1/auth/me` (no localStorage read) and sets the user; that `signOut` calls `POST /api/v1/auth/logout`. In `LoginPage.test.tsx`: assert login calls `setAuth` with the `user` (no token) and navigates. Mock `api` accordingly.

- [ ] **Step 2: Run — expect FAIL.** `cd frontend && rtk vitest run src/features/auth`

- [ ] **Step 3: Implement**
- `useAuth.tsx`: drop `tokenStorage` import. `setAuth` becomes `(authUser: AuthUser) => setUser(authUser)`; update `AuthContextType.setAuth` to `(user: AuthUser) => void`. Mount effect: always `api.get('/api/v1/auth/me').then(({user}) => setUser(user)).catch(() => setUser(null)).finally(...)` — no token check. `signOut`: `await api.post('/api/v1/auth/logout', {}).catch(() => {}); setUser(null);` (make `signOut` async or fire-and-forget).
- `LoginPage.tsx`: `const res = await api.post<{ user: AuthUser }>("/api/v1/auth/login", {email, password}); setAuth(res.user);`.

- [ ] **Step 4: Run — expect PASS.** `rtk vitest run src/features/auth`
- [ ] **Step 5: Commit** — `feat(fe): cookie-based auth context (no token storage)`

---

## Task 10: Frontend — axios withCredentials, drop tokenStorage + header sites

**Files:** Modify `frontend/src/shared/lib/apiClient.ts`, `frontend/src/features/chat/chatApi.ts`, `frontend/src/features/agencies/useAgencies.ts`; update their tests.

**Interfaces:** axios sends cookies (`withCredentials: true`), no `Authorization` anywhere, `tokenStorage` deleted.

- [ ] **Step 1: Update failing tests** — assert the two `fetch` calls include `credentials: 'include'` and no `Authorization` header; remove any test asserting the Bearer interceptor / `tokenStorage`.

- [ ] **Step 2: Run — expect FAIL.** `cd frontend && rtk vitest run src/features/chat src/features/agencies`

- [ ] **Step 3: Implement**
- `apiClient.ts`: add `withCredentials: true` to `axios.create({...})`; delete the request interceptor (Bearer) block and the `tokenStorage` export (the `TOKEN_KEY` const + object). Keep the response interceptor.
- `chatApi.ts` (`sendChatQuerySSE`): remove `const token = tokenStorage.get()` and the `...(token ? {Authorization…} : {})`; add `credentials: 'include'` to the `fetch` options; drop the `tokenStorage` import.
- `useAgencies.ts` (logo upload `fetch`): same — drop the manual `Authorization` header + `tokenStorage`, add `credentials: 'include'`.

- [ ] **Step 4: Run — expect PASS**, plus `./node_modules/.bin/tsc --noEmit` clean (no dangling `tokenStorage` references anywhere — grep to confirm).
- [ ] **Step 5: Commit** — `feat(fe): send session cookie via withCredentials; remove token storage`

---

## Task 11: Integration — full suites, surface parity, context.md

**Files:** Modify `backend/tests/test_surface_parity.py`, `context.md`.

- [ ] **Step 1:** Add `("POST", "/api/v1/auth/logout")` to the surface-parity expected set (it's an auth route reachable by all). Run `.venv/bin/pytest tests/test_surface_parity.py -v`.
- [ ] **Step 2:** Full backend suite `cd backend && .venv/bin/pytest -q` — green.
- [ ] **Step 3:** Full frontend suite `cd frontend && rtk vitest run` — green; `./node_modules/.bin/tsc --noEmit` clean.
- [ ] **Step 4:** Manual smoke (per `/run`, if runnable): login → response sets `session_id` cookie, body has no token; an authenticated GET works with only the cookie; `/responses` without an API key → 401; logout clears the cookie.
- [ ] **Step 5:** Update `context.md`: browser auth is now an opaque Redis session cookie (`session_id`, HttpOnly/Secure/SameSite=Lax, sliding re-rotate near expiry); JWT removed; API-key is the machine channel; `/responses`+`/conversations` require auth (no ephemeral users); frontend is header-free (`withCredentials`); new files `services/auth_session.py`, `middleware/session_refresh.py`; new settings. Note this is Phase A; C (anon `/chat` session) and D (WS cookie + WS-default) follow.
- [ ] **Step 6: Commit** — `docs: update context.md for cookie session auth (Phase A)`

---

## Self-Review

**Spec coverage:** session store (T2), cookie issuance/logout (T4), unified cookie+API-key resolution at both chokepoints (T3), sliding refresh (T5), JWT removal (T8), ephemeral removal + OpenAI-surface auth (T6), CORS credentials (T7), frontend header-free (T9–T10), settings (T1), context/parity (T11). ✓

**Placeholder scan:** every code step has concrete code; the only judgment calls (which existing tests reference `create_access_token`/ephemeral) are given as explicit grep-and-fix steps in T6/T8. ✓

**Type/name consistency:** `create_session`/`resolve_session`/`delete_session`/`remaining_ttl`, `_header_api_key`/`_resolve_api_key`/`_resolve_session_user`/`_resolve_role`, `SessionRefreshMiddleware`, `SESSION_COOKIE_NAME`/`AUTH_COOKIE_SECURE`/`SESSION_TTL_MINUTES`/`SESSION_REFRESH_BELOW_MINUTES` used consistently across producing/consuming tasks. ✓

**Cross-task risk:** T3 changes the signatures of `get_current_user*`/`enforce_role_allowlist` — any test/route passing `credentials=` breaks; T3 Step 4 and T8 Step 1 grep-and-fix sweep catches these. The `_resolve_token → _resolve_api_key` alias keeps the two WS callers working until Phase D.
