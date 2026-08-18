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
- **Role claim.** Read realm roles from `realm_access.roles`. Pick the highest
  of `admin` / `staff` / `user`. Default to `user` when none match.
- **`Principal`.** A frozen dataclass built from claims:
  `{ id: sub, email, display_name, role }` with an `is_admin` property.
  It replaces the `User` ORM object in request handling. `.id` is the Keycloak
  `sub`.

`app/auth/dependencies.py` keeps the same public names so routers do not change:
- `get_current_user_optional(request) -> Principal | None`
- `get_current_user(request) -> Principal`
- `require_admin(principal) -> Principal`
- `get_current_user_non_ephemeral` → becomes an alias of `get_current_user`
  (there is no ephemeral concept any more).

## 5. Role gate — logic unchanged

`enforce_role_allowlist` and every rule function
(`_is_public_get`, `_is_shared_write`, `_is_allowed_for_basic_user`,
`_is_allowed_for_staff`, `_STAFF_GET_EXACT`, the agent-proxy bypass) stay exactly
as written. Only `_resolve_role(conn)` changes: it reads the bearer token from
`conn.headers`, verifies it, and returns the role claim (or `None`). No DB read.

This is the seam that keeps the migration small at the router layer.

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
| `app/routers/users.py` | Keep the routes. Handlers now call `keycloak_admin` (see §8). Still `require_admin`. |
| `app/routers/api_key.py` | Delete. |
| `app/services/api_key.py`, `app/services/auth_session.py` | Delete. |
| `app/middleware/session_refresh.py` | Delete. Remove from `main.py`. |
| `app/auth/security.py`, `app/auth/ws.py` | Delete. |
| `app/models/user.py`, `app/models/session.py` | Delete. |
| `app/repositories/user.py` | Delete. Update `models/__init__.py` star-import. |
| `app/routers/chat.py` | Remove the WebSocket handler and its imports. Keep POST (JSON + SSE). |
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
- Ship a realm export JSON: the realm, the SPA public client (PKCE, redirect URIs,
  web origins), the confidential admin client, the `backend` audience mapper, the
  three realm roles (`admin`, `staff`, `user`), and one seed admin user.

## 10. Frontend contract (out of backend scope)

- Run OIDC Authorization Code + PKCE against the SPA public client.
- Send `Authorization: Bearer <access token>` on every API call.
- Drop the cookie/Supabase auth path and the API-keys page.
- Remove the chat WebSocket client; use the SSE stream.
- Refresh the access token with the refresh token; keep the access-token lifetime short.

## 11. Testing

- **Test keypair.** Tests generate a local RS256 keypair once. The verifier reads
  a test JWKS built from the public key. No live Keycloak in tests.
- **Helper.** `make_token(role="admin"|"staff"|"user", sub=..., email=...)` mints a
  signed token. A `no token` case covers guest.
- **Keep every role-allowlist test.** They now send minted tokens instead of
  cookies/keys. This proves the gate rules are unchanged.
- **New tests:** token verify (bad signature / wrong `aud` / expired → 401),
  guest chat (no token ⇒ chat works, `user_id` null), MCP anonymous + admin-header
  stripping, user-management proxy (mock the Admin API).
- TDD: write the failing test first for each unit (verifier, `_resolve_role`,
  proxy), confirm red, then implement.

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
