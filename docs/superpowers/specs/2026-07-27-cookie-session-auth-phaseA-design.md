# Cookie Session Auth — Phase A (Core) Design

**Date:** 2026-07-27
**Status:** Approved (brainstorming), pending implementation plan
**Branch:** `feat/auth-cookie-core` (off `dev`)
**Epic:** Migrate browser auth from localStorage JWT bearer to opaque HttpOnly session cookies, so WebSocket chat can authenticate via the auto-attached cookie and become the browser default. This is **Phase A** of a 3-phase epic (A → C → D; the originally-planned Phase B blocklist is eliminated — see §2).

## 1. Goal

Replace the stateless-JWT-in-header browser auth with an **opaque server-side
session** carried in an `HttpOnly` cookie, while keeping **API-key** auth (the
`tcg_` header) as a fully separate channel for machine clients. After Phase A the
browser sends **no `Authorization` header at all**, and the OpenAI-compatible
`/responses` + `/conversations` surfaces require a real authenticated caller
(no more auto-created ephemeral users).

## 2. Target auth model

Two separate channels:

| Caller | Credential | Resolution |
|---|---|---|
| Browser (SPA) | `session_id` cookie (opaque, `HttpOnly; Secure; SameSite=Lax`) | Redis lookup `session:<id> → user_id` → `User` |
| Machine / API client | `Authorization: Bearer tcg_<key>` | existing API-key hash lookup |

- **JWT bearer is removed entirely.** `create_access_token` / `decode_access_token`
  and the `JWT_SECRET` / `JWT_ALGORITHM` machinery are deleted. API-key hashing
  (`hash_api_key`, SHA-256) is independent and untouched.
- **Revocation is inherent.** Logout deletes the Redis session key; a request
  bearing a dead `session_id` resolves to anonymous. This removes the need for
  the originally-planned JWT `jti` blocklist — **Phase B is eliminated.**
- **CSRF:** the app is same-origin (single nginx gateway — see the deployment
  research), so `SameSite=Lax` alone is sufficient. State-changing endpoints are
  non-GET, and a `Lax` cookie is not sent on cross-site subrequests. No CSRF
  token is introduced.

## 3. Session store (Redis)

- New module `app/services/auth_session.py`. Reuse the existing async Redis
  client pattern from `app/services/rate_limit.py` (the `redis>=5.0.0` dep and
  `settings.REDIS_URL` already exist).
- Keys: `session:<uuid>` → the `user_id` (string). `EX = SESSION_TTL_MINUTES*60`.
- API (transport-free, unit-testable):
  - `create_session(user_id) -> session_id` — generate a UUID, `SET … EX ttl`.
  - `resolve_session(session_id) -> user_id | None` — `GET`; None if missing/expired.
  - `delete_session(session_id) -> None` — `DEL` (logout).
  - `create_session` is always used on login (never reuse an id) for
    session-fixation safety; the caller sets the new cookie.
  - `remaining_ttl(session_id) -> int | None` — Redis `TTL` in seconds (for the
    sliding-refresh check in §4.5).
- **`REDIS_URL` empty (single-worker dev):** `rate_limit.py` already degrades to
  an in-process fallback when Redis is absent. `auth_session` mirrors this with an
  in-process dict store so local dev without Redis still works. (Documented as
  dev-only; production sets `REDIS_URL`.)

## 4. Backend changes

### 4.1 Login — `app/routers/auth.py`
`POST /auth/login` verifies email/password (unchanged), then:
- `session_id = await create_session(user.id)`
- `response.set_cookie(SESSION_COOKIE_NAME, session_id, httponly=True,
  secure=settings.AUTH_COOKIE_SECURE, samesite="lax",
  max_age=settings.SESSION_TTL_MINUTES*60, path="/")`
- Response body returns **only** `{ "user": {…} }` — **no `access_token`** (JWT is
  gone; the session is the credential).

### 4.2 Logout — `app/routers/auth.py` (new)
`POST /auth/logout`: read the cookie, `await delete_session(session_id)`,
`response.delete_cookie(SESSION_COOKIE_NAME, path="/")`. Idempotent (no session →
still clears the cookie and 200s).

### 4.3 Unified caller resolution — `app/auth/dependencies.py`
Refactor both chokepoints to read the `Request` (not `HTTPBearer`), so they see
the header **and** the cookie. New internal helper:

```
resolve_caller(request) -> User | None:
  1. Authorization: Bearer <t>  present -> API-key path only (_resolve_api_key)
  2. else session cookie present -> resolve_session -> User
  3. else -> None
```

- `_resolve_token` loses its JWT branch (JWT removed); it becomes API-key-only
  (`_resolve_api_key`).
- `get_current_user` (required): 401 if `resolve_caller` is None.
- `get_current_user_optional`: None when no credential; **preserve the asymmetry**
  — a present-but-invalid **API key** still 401s (deliberate auth), a missing/expired
  **session cookie** degrades to anonymous (browser session token).
- `enforce_role_allowlist` + `_resolve_role`: refactor identically to read the
  request (header API-key **or** session cookie) so role-gating stays in lockstep
  with `get_current_user*`. `_resolve_role` keeps its no-side-effects contract
  (no `last_used_at` stamp, no rate-limit charge).
- `_is_shared_write` already lists `/api/v1/auth/` (covers the new `/auth/logout`).

### 4.4 Remove ephemeral / migrate OpenAI-compat surfaces
- Delete `app/services/openai/identity.py::owner_or_ephemeral` and the
  `X-Portal-Session` response-header logic in `app/routers/responses.py`.
- `app/routers/responses.py` and `app/routers/openai_conversations.py`: change the
  optional-user dependency to **required** auth (`get_current_user`) so anonymous
  callers get 401 instead of an auto-created ephemeral user. (API-key is the
  machine path; a logged-in browser session also satisfies it.)
- Remove any now-dead ephemeral-user helpers/imports.

### 4.5 Sliding session refresh (re-rotate near expiry)

A session should not expire out from under an actively-used browser. On any
request authenticated **via the session cookie** (not API-key), if the session's
remaining TTL is below the refresh threshold, **re-rotate** it:

1. `new_id = create_session(user_id)` (full TTL),
2. `delete_session(old_id)`,
3. `response.set_cookie(SESSION_COOKIE_NAME, new_id, …, max_age=SESSION_TTL_MINUTES*60)`.

- **Placement:** a single `SessionRefreshMiddleware` (Starlette HTTP middleware)
  so the logic lives in one place rather than being duplicated across the two
  auth chokepoints. It runs only when a session cookie is present; API-key
  requests and anonymous requests are untouched. The backend only serves `/api`
  (nginx serves the SPA), so the middleware never sees static assets.
- **Trigger:** `remaining_ttl < SESSION_REFRESH_BELOW_MINUTES*60`. Default is
  half the full TTL, so any activity in the back half of the window renews to
  full; a session idle past the full TTL still expires.
- **Concurrency:** two in-flight requests near the threshold may both rotate,
  orphaning one extra session that simply lives out its own TTL — benign and
  self-healing; no locking needed.
- **Transports:** covers HTTP (JSON + SSE — the `Set-Cookie` header is written
  before the SSE body streams). WebSocket refresh is Phase D.

### 4.6 CORS — `app/main.py`
Add `allow_credentials=True`; replace the wildcard `CORS_ORIGINS=["*"]` default
with an explicit origin list (`settings.CORS_ORIGINS`, defaulted to the
frontend origin). Wildcard + credentials is illegal; explicit origin is required
before credentialed requests work. Same-origin traffic is unaffected.

### 4.7 Settings — `app/config.py`
- Add `SESSION_COOKIE_NAME: str = "session_id"`.
- Add `AUTH_COOKIE_SECURE: bool = True` (set `False` only for pure-local
  plain-HTTP dev; tunnel/prod are HTTPS at the browser).
- Add `SESSION_TTL_MINUTES: int = 60*24*7` (7 days; carries the old
  `JWT_EXPIRE_MINUTES` value).
- Add `SESSION_REFRESH_BELOW_MINUTES: int = 60*24*3` (≈ half the TTL; the
  sliding-refresh trigger in §4.5).
- Remove `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` and the JWT
  production-secret assertion once JWT is deleted.

## 5. Frontend changes

- `shared/lib/apiClient.ts`: set `withCredentials: true` on the axios instance;
  **delete** the `Authorization` request interceptor and the entire `tokenStorage`
  (localStorage) module. No token is stored client-side anymore.
- `features/auth/useAuth.tsx`: login posts credentials and stores only the `user`
  from the body (cookie is set by `Set-Cookie`); mount-restore calls
  `GET /auth/me` (cookie auto-sent) to hydrate; `signOut` calls
  `POST /auth/logout` then clears user state. Remove all `tokenStorage` reads.
- `features/auth/LoginPage.tsx`: stop reading `access_token`; use the returned
  `user` only.
- Two raw-`fetch` sites drop the manual `Authorization` header and add
  `credentials: 'include'`: `features/chat/chatApi.ts` (SSE) and
  `features/agencies/useAgencies.ts` (logo upload).

## 6. Security considerations

- **XSS token theft eliminated** for the auth credential: an `HttpOnly` cookie is
  unreadable from JS (the localStorage JWT was not).
- **CSRF:** covered by `SameSite=Lax` on a same-origin deployment (§2). If a future
  deployment splits the SPA and API across sites, a CSRF token becomes required —
  documented as the one thing that would change.
- **Session fixation:** login always mints a fresh `session_id` (§3), and the
  sliding refresh (§4.5) rotates the id periodically over a long-lived session —
  a compromised id has a bounded useful life.
- **`Secure` flag:** on by default so the cookie never traverses plain HTTP in
  prod; `AUTH_COOKIE_SECURE=False` is the explicit dev-only escape hatch.
- **Cookie is opaque:** no user data in the cookie; server-side lookup only.

## 7. Breaking changes (documented, acceptable on `dev`)

- JWT bearer tokens are no longer accepted anywhere. Any client using a
  `/auth/login` JWT must switch to the session cookie (browser) or an API key.
- `/responses` + `/conversations` now require authentication (API key or session);
  anonymous calls get 401, and the `X-Portal-Session` ephemeral round-trip is gone.
- `/auth/login` no longer returns `access_token`.

## 8. Testing (TDD)

- Session store: create/resolve/delete/rotate; TTL expiry; in-process fallback
  when `REDIS_URL` empty.
- Login sets an `HttpOnly; Secure; SameSite=Lax` cookie with the right `Max-Age`;
  body has no `access_token`.
- A request authenticates via session cookie alone (no `Authorization`).
- API-key header still authenticates; when both present, header (API-key) wins.
- `get_current_user_optional` asymmetry: bad API key → 401; missing/expired
  session → anonymous.
- `enforce_role_allowlist` honors the session cookie (role gating via cookie).
- Logout deletes the session (subsequent cookie → anonymous) and clears the cookie.
- **Sliding refresh:** a cookie request with remaining TTL below the threshold
  re-rotates (new id set via `Set-Cookie`, old id deleted, fresh TTL); a request
  with ample TTL does **not** rotate; an API-key request never rotates.
- `/responses` + `/conversations` return 401 when anonymous; succeed with an API
  key; no ephemeral user is created.
- CORS: credentialed response headers; wildcard origin rejected with credentials.
- Frontend: no localStorage writes; axios `withCredentials`; `/me` restore path;
  logout calls the endpoint; the two `fetch` sites send `credentials: 'include'`
  and no `Authorization`.
- Regression: the removed JWT paths (`create_access_token`, JWT-branch tests) are
  deleted/rewritten; `test_surface_parity` gains `/auth/logout`.

## 9. Out of scope (later phases)

- **Phase C:** anonymous `/chat` gets a persistent anon session. Until then,
  anonymous `/chat` stays `user=None` as today (it never had ephemeral users).
- **Phase D:** WS handler reads the session cookie (auto-attached same-origin) and
  the browser chat flips to WS-default (SSE fallback). Phase A leaves WS on its
  current bearer path.

## 10. Risks

- **Two chokepoints must move in lockstep** (`get_current_user*` and
  `enforce_role_allowlist`/`_resolve_role`). A shared `resolve_caller` helper +
  tests guard this.
- **Redis dependency on the hot path.** Mitigated by the in-process fallback and
  Redis's speed; every authenticated request now does one `GET`.
- **Wide blast radius:** JWT removal + CORS + ephemeral removal touch many files.
  The plan sequences these so the suite stays green between tasks.
