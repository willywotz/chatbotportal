# Self-hosted OIDC Provider / IdP — Design

Date: 2026-09-23
Status: Approved (design decisions confirmed by user)
Branch: `feat/self-hosted-oidc`

## Goal

Remove the Keycloak service. Make the backend its own OIDC provider and
Identity Provider. Update the frontend to authenticate via OIDC. Greenfield:
no data migration from Keycloak. Keywords: JWKS, PKCE (S256), RS256.

## Decisions

- OIDC provider: hand-rolled on `pyjwt[crypto]` + `bcrypt` (both already
  present). No new backend dependency. Only the narrow flow the single
  first-party SPA client needs.
- Login UI: backend-rendered login page served at `/authorize`.
- Signing key: RS256 keypair persisted in Postgres, generated once at startup
  under the existing advisory-lock pattern; shared across `uvicorn --workers 4`.
- Frontend: `oidc-client-ts` replaces `keycloak-js` (like-for-like swap).

## Architecture

New backend package `app/auth/oidc/`:
- `keys.py` — RSA keypair lifecycle (load-or-generate, `kid`, JWKS serialization).
- `tokens.py` — mint/verify RS256 access + id tokens; scope/role claims.
- `provider.py` — grant machinery: authorization codes, PKCE verification,
  refresh-token rotation.
- `passwords.py` — bcrypt hash/verify.
- `scopes.py` — role→scope mapping (replicates realm composites).
- `router.py` — OIDC HTTP surface.

`app/auth/keycloak.py` is removed. `Principal`, `app/auth/dependencies.py`
(`get_current_user`, `require_scope`) keep their shape and behaviour; only
`principal_from_claims` changes to read flat `role`/`scope` claims. Per-route
`Security(require_scope, scopes=[…])` and the test `dependency_overrides`
contract are unchanged, so `tests/test_route_audit.py` stays green.

## Data model (Alembic migration, 4 new tables)

- `users` — `id UUID pk`, `email` (unique), `password_hash`, `display_name`,
  `role` (Enum user|staff|admin, `native_enum=False`, varchar), `is_active`,
  `created_at timestamptz`. `Conversation.user_id` keeps pointing at this id
  (plain nullable UUID, no hard FK — matches current `sub` semantics).
- `signing_keys` — `kid pk`, `private_pem`, `public_jwk jsonb`,
  `created_at timestamptz`, `is_active`.
- `oauth_auth_codes` — `code_hash pk`, `user_id`, `code_challenge`,
  `redirect_uri`, `scope`, `expires_at timestamptz`, `consumed`.
- `oauth_refresh_tokens` — `id`, `user_id`, `token_hash`, `expires_at`,
  `revoked`, `created_at`. Rotated per refresh; reuse of a rotated token
  revokes the chain.

Codes/refresh tokens live in Postgres (not in-memory) so all 4 workers share
them. Follows the model/repository conventions in MEMORY.md (module-level repo
funcs, `session` first arg, services never `commit()`).

## OIDC endpoints (issuer root, through Caddy — same origin as SPA + API)

- `GET /.well-known/openid-configuration` — discovery.
- `GET /.well-known/jwks.json` — active + recently-rotated public keys.
- `GET /authorize` — validate `client_id`, `redirect_uri`, `response_type=code`,
  `code_challenge`, `code_challenge_method=S256`, `state`, `scope`; render the
  server-side login page.
- `POST /authorize` — verify email+password (bcrypt), mint one-time code bound
  to `code_challenge`, redirect to `redirect_uri?code=…&state=…`.
- `POST /token` — `grant_type=authorization_code` (verify `code_verifier`
  against stored challenge) and `grant_type=refresh_token` (rotation). Returns
  `access_token` (RS256 JWT), `id_token`, `refresh_token`, `expires_in`,
  `token_type=Bearer`.
- `GET /userinfo` — bearer-protected; sub/email/name.

Lifetimes (env-overridable defaults): access 15 min, refresh 30 days
(rotating), code 60 s.

## Token claims & RBAC

Role→scope map in `app/auth/oidc/scopes.py`, replicating realm composites:
- `user`: agency:list, conversation:read:own, conversation:write:own, message:rate
- `staff`: + dashboard:read, executive:read, health:read, usage:read, feedback:read
- `admin`: + agency:read, agency:write, conversation:read:all, executive:write,
  analytics:read, feedback:read:detail, audit:read, connlog:read, llm:read,
  llm:write, settings:read, settings:write, popular:read, popular:write, user:manage

Access-token JWT: `iss`, `aud` (= `OIDC_ISSUER`; no separate audience knob),
`sub`, `email`, `name`, `role`, `scope` (space-delimited). `principal_from_claims`
reads flat `role`/`scope`.

## User management

`services/keycloak_admin.py` → `services/user_admin.py`: same public function
names (`list_users`, `get_user`, `create_user`, `update_user`, `set_enabled`,
`delete_user`) backed by a `users` repository with bcrypt. `routers/users.py`
keeps endpoints, `user:manage` scope, audit calls, self-delete guard — only the
import changes. `schemas/user.py` unchanged.

Startup seed: create `admin@chatbotportal.local` (role admin) if no admin
exists. Dev password from `SEED_ADMIN_PASSWORD` env (has a code default).

## Frontend

Remove `keycloak-js`; add `oidc-client-ts`. New `shared/lib/oidc.ts` wraps a
`UserManager` (authority = backend discovery URL, `VITE_OIDC_AUTHORITY`;
`VITE_OIDC_CLIENT_ID=chatbotportal-web`; `response_type=code`;
`code_challenge_method=S256`; silent renew via refresh token). Same exported
helpers as today (`login`, `logout`, `getToken`, `isAuthenticated`, `init`).
- `apiClient.ts` — interceptor gets/renews the token, attaches `Bearer`;
  401-relogin preserved.
- `useAuth.tsx`, `ProtectedRoute.tsx`, `main.tsx` — swap `keycloak.*` for the
  wrapper. MSW mock mode unchanged.
- New callback route `/auth/callback` completes the code exchange.
- Env vars `VITE_KEYCLOAK_*` → `VITE_OIDC_*`.

## Compose / config / deploy

- Delete the `keycloak` service, its `depends_on`, `deploy/keycloak/`.
- `config.py`: drop `KEYCLOAK_*`; add `OIDC_ISSUER`, `OIDC_ACCESS_TOKEN_TTL`,
  `OIDC_REFRESH_TOKEN_TTL`, `OIDC_CODE_TTL`, `OIDC_PRIVATE_KEY` (optional
  override), `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`. Every var has a code
  default (15-factor).
- `compose.yaml` / `.env.example`: `KEYCLOAK_*`/`VITE_KEYCLOAK_*` →
  `OIDC_*`/`VITE_OIDC_*`.
- Caddy: add `/.well-known/*`, `/authorize`, `/token`, `/userinfo` → backend.

## Testing (TDD red→green→refactor)

Backend (real Postgres testcontainer): key generate/rotate + JWKS; token
mint/verify (RS256, iss/aud/exp, tamper→InvalidToken); authorize→token PKCE
happy path + failures (bad verifier, expired/replayed code, wrong
redirect_uri); refresh rotation + reuse-revocation; `principal_from_claims`;
`user_admin` CRUD + bcrypt; discovery doc shape. `test_route_audit.py` stays
green; conftest Principal override unchanged.

Frontend (vitest): `oidc.ts` wrapper (mocked `UserManager`), `apiClient` token
attach/refresh, `useAuth`/`ProtectedRoute`, MSW `/authentication/me`.

## Sequencing

Backend first (keys → tokens → provider → router → user_admin → seed →
config/wire-up), then frontend, then compose/deploy, then docs. Update
`MEMORY.md` auth section and run `graphify update .` at the end.
