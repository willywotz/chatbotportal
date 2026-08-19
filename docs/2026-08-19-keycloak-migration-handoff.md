# Keycloak Auth Migration — Handoff (2026-08-19)

Replaces the portal's local password/session/API-key auth with **Keycloak (OIDC)**.
Backend and frontend both migrated, build clean, and validated end-to-end in a browser
against a full `docker compose` stack (login → scoped APIs → user management → account console).

- **Spec:** `docs/superpowers/specs/2026-08-18-keycloak-auth-migration-design.md`
- **Plans:** `docs/superpowers/plans/2026-08-18-keycloak-auth-migration.md` (backend),
  `docs/superpowers/plans/2026-08-19-frontend-keycloak-oidc.md` (frontend)
- **SDD ledgers** (per-task decisions/rulings): `.superpowers/sdd/2026-08-18-keycloak-auth-migration/progress.md`,
  `.superpowers/sdd/2026-08-19-frontend-keycloak-oidc/progress.md`

## Branches & how to integrate

| Branch | Base | Commits | Content |
| --- | --- | --- | --- |
| `feat/keycloak-auth-migration` | `main` | 34 | Backend + Keycloak realm/compose |
| `feat/frontend-keycloak-oidc` | `feat/keycloak-auth-migration` | +15 | Frontend SPA + browser-surfaced fixes |

The frontend branch sits **on top of** the backend branch, so it contains everything.
Recommended: merge **`feat/frontend-keycloak-oidc` → `main`** (`--no-ff`) as one atomic
migration (49 commits). Or merge the backend branch first, then the frontend branch.
Every task was reviewed with fresh context; both branches passed a final whole-branch review.

**Not merged yet** — the merge is the owner's call.

## End state (what changed)

### Auth model
- **Keycloak OIDC.** No local `users`/`sessions`/`user_api_keys` tables, no `tcg_` API keys,
  no passwords, no cookies. Identity lives in Keycloak.
- **Backend** verifies the bearer access token locally against cached JWKS
  (`backend/app/auth/keycloak.py::verify_token`, RS256) → a `Principal`
  (`{id=sub, email, display_name, role, scopes}`).
- **Authorization = per-route scopes.** Each protected route declares
  `Security(require_scope, scopes=[...])`. There is **no runtime global gate**; the
  "no route silently unprotected" guarantee is the CI test `backend/tests/test_route_audit.py`
  (every `/api/v1` route is public, whitelisted, or scope-guarded — 74 routes, 0 offenders).
- **Anonymous surface = `/api/v1/public/*`** (guest chat `POST /api/v1/public/chat`, public
  status/popular-questions, agency-logo GET) + `/api/v1/agent-proxy/*` (OneChat callback) +
  `GET /api/v1/authentication/me`.
- **Roles → scopes live in Keycloak.** Composite realm roles `user`/`staff`/`admin` bundle
  `backend` client-roles (the scope names). Ownership is scope-based
  (`conversation:read:all` vs `:own`), not role-based.
- **User management** proxies to the Keycloak Admin REST API
  (`backend/app/services/keycloak_admin.py`, `user:manage`). **MCP** verifies a Keycloak
  bearer, else anonymous.

### Frontend (React/Vite SPA)
- **`keycloak-js`** (`frontend/src/shared/lib/keycloak.ts`), `check-sso` init at boot (guests
  pass), bearer + silent refresh in the axios client, `useAuth` from `/me`, `ProtectedRoute`
  redirects to Keycloak login on demand, `LoginPage` is a redirect button.
- Chat + agency queries → `/api/v1/public/chat`; logo GET → `/public`; raw fetches (SSE, logo
  upload) attach the bearer; no `credentials:'include'`.
- **Removed:** API-keys feature, chat WebSocket, usage-by-API-key view, change-password dialog
  (→ Keycloak account-console link). Client-side role gating is **UX-only**; the backend scopes
  are the real control.

### Data migration
- aerich migration `30_20260819092527_drop_local_auth.py` drops `users`/`sessions`/`user_api_keys`
  (CASCADE); `conversations.user_id` / `messages.user_id` become plain UUID columns (Keycloak sub).

## Deploy checklist (production, non-localhost)

**These must be set before a real-domain rollout** (dev defaults work for local compose):

1. **URLs** — the public `/auth` origin must be consistent across all four:
   - `KEYCLOAK_URL` = `https://<domain>/auth` (backend token issuer)
   - `VITE_KEYCLOAK_URL` = `https://<domain>/auth` (baked into the SPA at **build time**)
   - `KEYCLOAK_INTERNAL_URL` = `http://keycloak:8080/auth` (backend → Keycloak on the compose net)
   - realm `portal-spa.redirectUris` must include `https://<domain>/*`
2. **Secrets (override the committed dev placeholders):**
   - `KEYCLOAK_ADMIN_CLIENT_SECRET` = the real `portal-admin` client secret
   - `KEYCLOAK_BOOTSTRAP_PASSWORD` = a strong Keycloak admin password
   - realm-export seed admin `admin/admin` and `portal-admin-dev-secret` are **dev only**
3. **Keycloak mode** — compose uses `start-dev`. For a hardened prod, switch to `start` and set
   `KC_HOSTNAME` to the public URL (behind Caddy at `/auth`, `KC_PROXY_HEADERS=xforwarded` is set).
4. **DB migration** — run `aerich upgrade` against prod Postgres (migration 30 is included and
   validated; the whole 0→30 chain applies on a fresh DB). Fresh DB via compose `init_db`
   also runs `generate_schemas(safe=True)`.
5. **Gateway** — Caddy serves the SPA, `/api` → backend, `/auth/*` → keycloak, `/jaeger` → jaeger.
   Keycloak is **not** published on a host port (behind Caddy, like Jaeger).
6. `release.yaml` uses `docker compose -f compose.yaml up` (no override) → **production** frontend
   (static nginx, `VITE_*` baked via build args). Ensure `VITE_KEYCLOAK_URL` is in the build env.

## Local dev run

The four URLs must name the **same origin**, and the gateway port must be free & stable. Copy
`.env.example` → `.env` and set a free port (host `:8080` is often taken):

```
EXTERNAL_HTTP_PORT=8090
KEYCLOAK_URL=http://localhost:8090/auth
VITE_KEYCLOAK_URL=http://localhost:8090/auth
KEYCLOAK_ADMIN_CLIENT_SECRET=portal-admin-dev-secret   # matches the realm dev secret
```

Then `docker compose up -d --build` (auto-merges `compose.override.yaml` → Vite dev server with
hot reload). Open `http://localhost:8090`, log in with **`admin` / `admin`**.

- With **no `.env`**, the gateway gets a *random* port → the SPA's baked `:8080` won't match →
  OIDC fails (`3p-cookies/step1.html` 404 / iframe timeout). Always pin `.env` for browser login.
- `-f compose.yaml` (no override) runs the **production** nginx frontend instead (what CI/prod use).

## realm-export completeness (why it needed fixes)

The realm was hand-authored, so several conventions a normally-created Keycloak realm gets for
free were missing. All are now in `deploy/keycloak/realm-export.json`, so a fresh `--import-realm`
comes up correct — but the file is the reference if you rebuild the realm elsewhere:

- `portal-spa.redirectUris` include the gateway origins (`:8080/:8090/:5173`); `webOrigins: "+"`.
- `portal-admin` service account has `realm-management`: `view-users, manage-users, view-realm,
  manage-realm` (needed to read + assign realm roles when creating users).
- Seed `admin` user has `default-roles-chatbotportal` (grants `account` roles → account console).
- Realm `defaultDefaultClientScopes = [web-origins, acr, roles, profile, basic, email]` so
  **built-in** clients (account-console/account/security-admin-console) emit `resource_access`
  (without this, the account console 403s — its token had no roles).
- `backend` client roles = the scope taxonomy; composite realm roles `user/staff/admin` bundle them.
- A `backend-audience` client scope is a default scope on `portal-spa`/`portal-admin` so tokens
  carry `aud: backend` (the backend's audience check).

## Known follow-ups (non-blocking)

- **User-create is not transactional** (`keycloak_admin.create_user`): it POSTs the user then
  assigns the role in two steps with no rollback — a mid-failure leaves a role-less user. Now that
  the service account has the right roles it won't trigger; a clean fix deletes the user on
  role-assignment failure.
- **Admin proxy folds Keycloak 5xx → HTTP 400** (`_map_error`) — masks an upstream outage as a
  client error; consider surfacing 5xx distinctly.
- **6 pre-existing OTEL/traceparent test failures** in the backend suite — fail on `main` too,
  unrelated to this migration.
- **Frontend lint** has ~50 pre-existing problems in unrelated files (supabase functions,
  tailwind.config) — unchanged by this work.
- **Committed deploy key** at `deploy/deploy_key` (pre-existing, unrelated) — worth rotating.

## Rollback

Both branches are unmerged; not integrating is the rollback. If merged and you must revert:
`git revert` the merge commit, then in prod restore the pre-migration image and DB (migration 30
drops tables — restore from a pre-migration backup; there is no down-migration for the dropped
user data).

## Verification (already done, re-runnable)

- Backend: `cd backend && OTEL_SDK_DISABLED=true uv run pytest -q` → green except the 6 OTEL tests;
  `uv run pytest -q tests/test_route_audit.py` → 0 unprotected routes.
- Frontend: `cd frontend && npx tsc -b tsconfig.app.json --noEmit` (0 errors) and `pnpm test` (409).
- Stack: `docker compose up -d --build`; a real Keycloak token via Caddy `/auth` → backend `/me`
  200, garbage token 401, scoped route without token 401, public status 200; user-management
  create/list 200/201; account console 200.
