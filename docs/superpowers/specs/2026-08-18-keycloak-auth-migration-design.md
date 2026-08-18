# Keycloak Auth Migration — Design

- Date: 2026-08-18
- Status: Approved for planning
- Scope: Backend (`backend/`). Frontend contract noted, but frontend work is separate.
- Relation to other work: Independent of the planned Tortoise → SQLAlchemy migration. This design stays on Tortoise + aerich.

## 1. Goal

Replace the backend's own identity and access system with Keycloak as the single
identity provider (IdP). The backend stops storing passwords, sessions, and API
keys. It trusts a Keycloak-signed access token (OIDC) on each request.

## 2. Decisions (locked)

| Topic | Decision |
| --- | --- |
| Guest chat | Keep open. No login needed to chat. No user is attached (`user_id` = null). |
| Identity store | Full Keycloak. Drop the local `users` table. Rows store the Keycloak `sub` directly. |
| Token transport | `Authorization: Bearer <access token>`. The SPA is a public client and uses Authorization Code + PKCE. |
| Token check | Local JWKS verification (stateless). No per-request call to Keycloak. |
| Data migration | Greenfield. No production users to migrate. Seed one admin in Keycloak. |
| Chat WebSocket | Drop it. Chat keeps JSON and SSE only. |
| User management | Keep the portal Users page. Proxy it to the Keycloak Admin REST API. |
| Authorization model | Keycloak owns role → permission. Endpoints declare a required scope. No code allow-list. |
| Gate posture | Fail-closed. Every `/api/v1` route needs a valid token except the `/api/v1/public/*` namespace. |
| Anonymous surface | A URL namespace (`/api/v1/public/*`), not a list. Guest chat and the logo move there; agent-proxy becomes its own mount. |
| Invalid token | Reject at the gate with 401. `no token` (guest) and `bad token` (401) are different. |

## 3. End state

**Removed**
- Local password login, `bcrypt` (`app/auth/security.py`).
- `sessions` table, `app/models/session.py`, `app/services/auth_session.py`, `app/middleware/session_refresh.py`.
- `user_api_keys` table, `app/routers/api_key.py`, `app/services/api_key.py`, the API-key part of `app/models/user.py`.
- Anonymous / ephemeral users, `POST /api/v1/authentication/anonymous`, `is_ephemeral`.
- `users` table, `app/models/user.py` (`User`), `app/repositories/user.py`.
- Chat WebSocket: the `@router.websocket` handler in `app/routers/chat.py`, `app/services/chat/ws.py`, `app/auth/ws.py`, `ConnectionRegistry`.

**Added**
- `app/auth/keycloak.py`: JWKS cache + token verify + `Principal`.
- `app/services/keycloak_admin.py`: Admin REST client for user management.
- A Keycloak service in `compose.yaml` with a realm export.

## 4. Auth core

New module `app/auth/keycloak.py`.

- **JWKS cache.** On first use, fetch the realm keys from
  `{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/certs`. Cache them.
  Refresh on an unknown `kid` (key rotation), with a short minimum refresh interval.
- **Verify.** For a bearer token: check the RS256 signature, `iss`
  (`{KEYCLOAK_URL}/realms/{REALM}`), `aud` (`KEYCLOAK_AUDIENCE`), and `exp`.
  On any failure raise 401. No token present ⇒ guest (return `None` where the
  caller allows it).
- **Scopes.** Read the effective permission set from
  `resource_access.backend.roles` (the `backend` client roles the token grants).
  Also read the coarse realm role (`realm_access.roles`) for display only.
- **`Principal`.** A frozen dataclass built from claims:
  `{ id: sub, email, display_name, role, scopes: frozenset[str] }` with an
  `is_admin` property (kept only for display; authz uses `scopes`).
  It replaces the `User` ORM object in request handling. `.id` is the Keycloak
  `sub`.

`app/auth/dependencies.py` public surface:
- `get_current_user_optional(request) -> Principal | None` — guest returns `None`;
  a present-but-invalid token raises 401.
- `get_current_user(request) -> Principal` — requires a valid token.
- `get_current_user_non_ephemeral` → alias of `get_current_user` (no ephemeral
  concept any more).
- `require_scope` — a `Security` dependency (see §5.2). `require_admin` is removed;
  admin-only routes require an admin-only scope instead.

> **SUPERSEDED DURING IMPLEMENTATION (2026-08-19, user-approved).** The runtime
> `enforce_access` gate described in §5.1 and the agent-proxy ASGI re-mount in §5.1a/§7
> were NOT built. A super-advisor consult found the runtime gate redundant with per-route
> `require_scope` and incompatible with the test suite's override-based auth. Final design
> (**Path X**): authorization is per-route `require_scope` (deny-by-default: no valid token
> ⇒ 401, missing scope ⇒ 403); the "no route silently unprotected" guarantee is the CI test
> `tests/test_route_audit.py`; there is NO runtime global gate; agent-proxy stays a plain
> anonymous router (no re-mount), whitelisted in the route-audit. See the ledger rulings and
> the "Auth & RBAC" section of `CONTEXT.md`. The rest of this section is retained as the
> design's reasoning; read §5.2–§5.5 as built, §5.1/§5.1a as superseded.

## 5. Authorization — fail-closed gate + Keycloak scopes

The old code allowlist is replaced. Authorization decisions (which role may reach
which resource) move into Keycloak. The code keeps only the fail-closed gate and a
single anonymous URL namespace — no per-endpoint list.

### 5.1 The gate (`app/auth/dependencies.py`, rename `enforce_role_allowlist` → `enforce_access`)

Runs once per request as the global dependency. There is **no endpoint allow-list** —
the anonymous surface is a URL namespace, not a maintained list:

```
path not under /api/v1/ ?             → pass   (health, docs, redoc, openapi, sub-app mounts)
path under /api/v1/public/ ?          → pass   (auth-optional zone; token read if present, never required)
token missing?                        → 401
token invalid (sig / iss / aud / exp) → 401
else                                  → pass to the route's own require_scope
```

- The gate knows **no role rules**. It enforces only: in the public namespace, or a
  valid token.
- **`/api/v1/public/*` is the auth-optional zone.** `public` means *token not
  required*, not *token forbidden* — an authenticated caller still sends a bearer,
  and it is still read (e.g. to attach `user_id` on guest chat).
- Everything that must be reachable without a token lives under this one prefix, so
  adding a future anonymous endpoint is a routing choice, not a gate edit.
- `GET /authentication/me` is the one **authenticated-but-scope-free** route: it needs
  a valid token (the gate enforces it) but no scope. The route-audit test (§5.5)
  whitelists it explicitly.

### 5.1a Routes that move into the public namespace

| Endpoint | From | To |
| --- | --- | --- |
| Guest chat | `POST /api/v1/chat` | `POST /api/v1/public/chat` |
| Agency logo | `GET /api/v1/agencies/{id}/logo` | `GET /api/v1/public/agencies/{id}/logo` |
| Public status / popular questions | already `/api/v1/public/...` | unchanged |

`agent-proxy` leaves the gate entirely: it is re-mounted as its own ASGI sub-app
(see §7), like `/mcp`. Mounts bypass FastAPI dependencies, so no gate exception is
needed for it.

### 5.2 Per-route scope — `require_scope`

Each authenticated route declares the permission it needs with FastAPI's native
`SecurityScopes`:

```python
from fastapi import Security
from app.auth.dependencies import require_scope

@router.get("/dashboard/statistics")
async def statistics(p: Principal = Security(require_scope, scopes=["dashboard:read"])):
    ...
```

`require_scope` reads the verified `Principal`, checks that `scopes` ⊆
`principal.scopes`, and raises **403** otherwise. `require_admin` is deleted; an
admin-only route simply requires a scope only the `admin` composite role holds.

### 5.3 Scopes carried by Keycloak

- Define **`backend` client roles** = the permission names:
  `agency:read`, `agency:write`, `dashboard:read`, `executive:read`,
  `executive:write`, `health:read`, `usage:read`, `feedback:read`, `feedback:write`,
  `audit:read`, `llm:read`, `llm:write`, `settings:read`, `settings:write`,
  `popular:write`, `conversation:read:own`, `conversation:read:all`, `user:manage`.
- Define **composite realm roles** `admin` / `staff` / `user` that bundle the client
  roles. This is where "staff may view the ops dashboards" now lives — in the realm,
  not in code. Granting a role a new permission is a Keycloak change, no deploy.
- The token carries the effective set in `resource_access.backend.roles`.

### 5.4 Ownership becomes a scope, not a role check

Today's own-or-admin logic (`services/conversation.py`, `services/similarity.py`,
history routes) changes: a token with `conversation:read:all` sees every
conversation; otherwise `conversation:read:own` filters to `principal.id` (the
`sub`). No `role == "admin"` literals remain in services.

### 5.5 Route-audit test (second net)

A test walks every registered FastAPI route and asserts each `/api/v1/*` route is
**either** under `/api/v1/public/` **or** carries a `require_scope` dependency (with a
one-entry whitelist for `GET /authentication/me`). A new protected endpoint that
forgets its scope fails CI, closing the silent-open footgun structurally.

## 6. Data model and migration

- Drop tables: `users`, `sessions`, `user_api_keys`.
- `conversation.user` (FK) → `user_id = fields.UUIDField(null=True)`.
- `message.user` (FK) → `user_id = fields.UUIDField(null=True)`.
- Pattern already exists: `llm_usage.user_id` is a plain nullable `UUIDField`.
- `audit` keeps `actor_email`, written from the token claim at call time.
- One aerich migration: drop the three tables and alter the two FK columns to
  plain UUID columns. Greenfield, so no backfill.

Note: `save_turn` and `conversation`/`message` repositories change only where they
set the user relation — they now set `user_id=principal.id if principal else None`.

## 7. Routers and services

| File | Action |
| --- | --- |
| `app/routers/auth.py` | Keep only `GET /authentication/me` (return the Principal). Delete login, logout, anonymous, change-password. |
| every authenticated router | Add a `Security(require_scope, scopes=[...])` dependency per route (§5.2). Remove `Depends(require_admin)` / `Depends(get_current_user)` role checks in favor of the scope. |
| `app/routers/users.py` | Keep the routes; each requires `user:manage`. Handlers now call `keycloak_admin` (see §8). |
| `app/routers/api_key.py` | Delete. |
| `app/services/api_key.py`, `app/services/auth_session.py` | Delete. |
| `app/middleware/session_refresh.py` | Delete. Remove from `main.py`. |
| `app/auth/security.py`, `app/auth/ws.py` | Delete. |
| `app/models/user.py`, `app/models/session.py` | Delete. |
| `app/repositories/user.py` | Delete. Update `models/__init__.py` star-import. |
| `app/routers/chat.py` | Remove the WebSocket handler and its imports. Move the POST to the `/public/chat` prefix (auth-optional, JSON + SSE). |
| `app/routers/agencies/logo.py` | Move the logo GET under `/public` → `/api/v1/public/agencies/{id}/logo`. |
| `app/routers/agent_proxy.py` | Re-mount as its own ASGI sub-app in `main.py` (`app.mount("/api/v1/agent-proxy", ...)`), outside the gate, like `/mcp`. Auth unchanged (UUID + agency credentials). |
| `app/services/chat/ws.py` | Delete. |
| `app/services/chat/stream.py`, `turn.py` | Set `user_id` from the Principal; no other change. |
| `app/mcp/server.py` | `AuthMiddleware` verifies a Keycloak bearer when present (same JWKS path), else anonymous. `user_is_admin` from the role claim. OneChat loop unchanged. |
| `app/services/seed.py` | Remove `run_seed_admin`. Keep `run_seed_agencies`. Remove the call from `main.py` lifespan. |
| `app/services/analytics/usage.py` | Drop API-key attribution. Attribute usage by `user_id` (sub). |
| `app/services/usage_context.py` | Drop `current_api_key_id`. Keep `current_user_id`, set from the Principal. |

## 8. User management proxy (`app/services/keycloak_admin.py`)

The portal keeps its admin Users page, backed by the Keycloak Admin REST API.

- **Auth to Keycloak.** A confidential client (`KEYCLOAK_ADMIN_CLIENT_ID` /
  `KEYCLOAK_ADMIN_CLIENT_SECRET`) with the `realm-management` roles
  (`view-users`, `manage-users`). Get a token with the client-credentials grant.
  Cache it until near expiry.
- **Map the portal user routes to Admin API calls:**
  - `GET ""` (list) → `GET /admin/realms/{realm}/users` (+ paging/search).
  - `POST ""` (create) → `POST /admin/realms/{realm}/users`, then assign a realm role.
  - `GET /{id}` → `GET /admin/realms/{realm}/users/{id}`.
  - `PATCH /{id}` (update role / profile) → `PUT .../users/{id}` and role-mapping calls.
  - `POST /{id}/deactivate` → `PUT .../users/{id}` with `enabled=false`.
  - `POST /{id}/activate` → `PUT .../users/{id}` with `enabled=true`.
- Translate the Keycloak user representation to the existing `schemas/user.py`
  shapes, so the frontend contract does not change.
- Errors from Keycloak map to clean HTTP errors (404 for missing user, etc.).

## 9. Config and infra

New env (15-Factor; add to `app/config.py` and compose):
- `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID` (SPA public client),
  `KEYCLOAK_AUDIENCE`, `KEYCLOAK_ADMIN_CLIENT_ID`, `KEYCLOAK_ADMIN_CLIENT_SECRET`.
- `KEYCLOAK_JWKS_URL` is derived from URL + realm; no separate var needed.

Remove: `SESSION_*`, `SESSION_COOKIE_NAME`, `AUTH_COOKIE_SECURE`, and API-key
settings.

Keycloak service:
- Add a Keycloak container to `compose.yaml`.
- Ship a realm export JSON that defines:
  - the realm and the SPA public client (PKCE, redirect URIs, web origins);
  - the confidential admin client (client-credentials, `realm-management` roles);
  - the `backend` client + audience mapper, and its client roles = the permission
    scopes listed in §5.3;
  - the three composite realm roles `admin` / `staff` / `user`, each bundling the
    client-role scopes it grants (the role → permission map);
  - one seed admin user with the `admin` realm role.
- The role → scope bundling in this export is the authoritative authorization
  policy. Changing what `staff` may do is an edit here, not a code change.

## 10. Frontend contract (out of backend scope)

- Run OIDC Authorization Code + PKCE against the SPA public client.
- Send `Authorization: Bearer <access token>` on every API call.
- Drop the cookie/Supabase auth path and the API-keys page.
- Update two moved URLs: chat `POST /api/v1/chat` → `/api/v1/public/chat`, and the
  agency logo `GET /api/v1/agencies/{id}/logo` → `/api/v1/public/agencies/{id}/logo`.
- Remove the chat WebSocket client; use the SSE stream.
- Refresh the access token with the refresh token; keep the access-token lifetime short.

## 11. Testing

- **Test keypair.** Tests generate a local RS256 keypair once. The verifier reads
  a test JWKS built from the public key. No live Keycloak in tests.
- **Helper.** `make_token(scopes=[...], sub=..., email=..., role=...)` mints a signed
  token with the given `resource_access.backend.roles`. A `no token` case covers guest.
- **Rewrite the old allowlist tests as scope tests.** Each asserts that a token
  lacking a route's scope gets 403 and a token with it gets 200 — the same access
  matrix, now expressed as scopes.
- **Route-audit test (§5.5).** Walk every route; each must be public/guest or carry
  `require_scope`. Fails on an unclassified route.
- **New tests:** token verify (missing → 401; bad signature / wrong `aud` / expired →
  401), scope check (`require_scope` 403 on missing scope), guest chat (no token ⇒
  chat works, `user_id` null), ownership scope (`conversation:read:own` vs `:all`),
  MCP anonymous + admin-header stripping, user-management proxy (mock the Admin API).
- TDD: write the failing test first for each unit (verifier, `enforce_access`,
  `require_scope`, proxy), confirm red, then implement.

## 12. Non-goals

- No SQLAlchemy migration here.
- No self-service registration flow in the portal (Keycloak owns it).
- No offline tokens or service accounts for third-party API callers (the local
  API-key feature is removed; programmatic callers use Keycloak tokens later if needed).

## 13. Cutover

Greenfield, so a single branch:
1. Stand up Keycloak with the realm export.
2. Land the backend branch (delete old auth, add JWKS verifier + admin proxy, drop
   tables via one aerich migration).
3. Land the frontend OIDC change.
4. Seed the admin in Keycloak; verify login, chat (guest + user), admin pages, MCP,
   and the OneChat loop.

## 14. Risks

- **Token revocation lag.** Local JWKS means a token is valid until `exp`. Mitigate
  with a short access-token lifetime (e.g. 5 minutes) and refresh tokens.
- **Admin client secret.** Store `KEYCLOAK_ADMIN_CLIENT_SECRET` only in env, never in
  git. (Note: an unrelated deploy key is already committed at `deploy/deploy_key`;
  out of scope here but worth rotating.)
- **JWKS availability at startup.** Fetch lazily and cache; do not block startup on
  Keycloak being up.
