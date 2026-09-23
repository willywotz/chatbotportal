# Frontend Keycloak OIDC Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the React SPA from the removed cookie/password auth to Keycloak OIDC (Authorization Code + PKCE), send a bearer token on every API call, and update the endpoints the backend migration moved or removed.

**Architecture:** A single `keycloak-js` instance is initialized once at app boot with `onLoad: 'check-sso'` (guests pass through — guest chat and public pages stay open; login is triggered on demand). The axios client attaches `Authorization: Bearer <access token>` from that instance and refreshes it before expiry. `useAuth` derives the user from the backend's `GET /authentication/me` (now bearer-authed). Route guards trigger a Keycloak login redirect instead of a local login form. The API-keys feature and the usage-by-API-key view are deleted; guest chat and the agency logo move under `/api/v1/public/`.

**Tech Stack:** React 18, Vite, TypeScript, axios, @tanstack/react-query, react-router-dom, vitest + MSW. **New dependency:** `keycloak-js`.

**Spec / backend contract:**
- `docs/superpowers/specs/2026-08-18-keycloak-auth-migration-design.md` (§10 frontend contract)
- `CONTEXT.md` → "Auth & RBAC (Keycloak)" and the frontend-handoff notes
- Backend realm: `deploy/keycloak/realm-export.json` (SPA client `portal-spa`, public, PKCE S256, audience `backend`)

## Global Constraints

- **OIDC library = `keycloak-js`** (the official Keycloak adapter). Rationale: it maps 1:1 to the realm's `portal-spa` public client, does PKCE + silent refresh out of the box, and is a single small dep. *Alternative considered:* `react-oidc-context`/`oidc-client-ts` (more React-idiomatic hooks, provider-agnostic) — pick that only if the team wants provider independence. This plan assumes `keycloak-js`. **Confirm before Task 1 if you disagree.**
- **Bearer, not cookies.** Remove `withCredentials`; attach `Authorization: Bearer` from the Keycloak instance. Backend CORS is bearer-safe.
- **Public/guest surface stays open**: `POST /api/v1/public/chat`, public status/popular-questions, and `GET /api/v1/public/agencies/{id}/logo` need NO token. A logged-in user still sends their token to `/public/chat` (to attach `user_id`).
- **Client-side role gating is UX-only.** The backend enforces scopes; `ProtectedRoute`/`roles.ts` only decide what to *show*. Never treat the client guard as security.
- Keep tests green (`pnpm test`) after each task. TDD where a unit boundary exists (token→user mapping, the axios interceptor, URL builders); OIDC init is integration-tested with a mocked `keycloak-js`.
- Env: new `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_REALM`, `VITE_KEYCLOAK_CLIENT_ID`. `VITE_KEYCLOAK_URL` is the public `/auth` base (e.g. `http://localhost:8080/auth` dev, `https://<domain>/auth` prod).

---

## Endpoint & feature change map (source of truth)

| Change | Frontend touch points |
| --- | --- |
| Guest chat `POST /api/v1/chat` → `POST /api/v1/public/chat` | `features/chat/chatApi.ts` (JSON `sendChatQuery` L42, SSE `streamChatSSE` L113) |
| Chat WebSocket removed (backend WS deleted) | `features/chat/chatApi.ts` `sendChatQueryWS` (L~212) + its caller |
| Logo image GET → `/api/v1/public/agencies/{id}/logo` | backend now STORES the `/public` URL in `agency.logo`; `AgencyLogo` renders it as-is. Verify `features/agencies/useAgencies.ts:127` (logo fetch) uses the value from the API, not a hardcoded path |
| Auth: `/authentication/{login,logout,anonymous,change-password}` removed; only `GET /me` remains | `features/auth/useAuth.tsx`, `LoginPage.tsx`, `ChangePasswordDialog.tsx` |
| API-keys feature removed (backend routes deleted) | `features/api-keys/*`, `App.tsx` (route L107 + redirect L115 + lazy import L31), `features/settings/SettingsLayout.tsx` (tab L17), `features/auth/roles.ts` (`/api-keys`, `/settings/api-keys`) |
| Usage `group_by=api_key` view retired | `features/usage/usageApi.ts:14`, `features/usage/UsageAnalyticsPage.tsx:15`, SettingsLayout tab L18 label |
| Anonymous session removed | `useAuth.ensureSession`, `AuthUser.isEphemeral`, callers |

---

## File structure

- **New:** `src/shared/lib/keycloak.ts` — the singleton + init/token helpers.
- **New:** `src/features/auth/keycloak.env.ts` — typed env accessor (optional; may fold into keycloak.ts).
- **Modify:** `src/main.tsx` (init Keycloak before render), `src/shared/lib/apiClient.ts`, `src/features/auth/useAuth.tsx`, `src/features/auth/ProtectedRoute.tsx`, `src/features/auth/LoginPage.tsx`, `src/features/chat/chatApi.ts`, `src/features/auth/roles.ts`, `src/features/settings/SettingsLayout.tsx`, `src/features/usage/{usageApi.ts,UsageAnalyticsPage.tsx}`, `src/App.tsx`, `src/mocks/handlers.ts`, `.env.example` (frontend or root), `vite` env types (`src/vite-env.d.ts`).
- **Delete:** `src/features/api-keys/*`, `src/features/auth/ChangePasswordDialog.tsx`.

---

## Phase 1 — Keycloak instance + bearer transport

### Task 1: Add keycloak-js, the singleton, and env

**Files:** `package.json`; create `src/shared/lib/keycloak.ts`; modify `src/vite-env.d.ts`; `.env.example`.

**Interfaces:**
- Produces: `keycloak` (a `Keycloak` instance), `initKeycloak(): Promise<boolean>` (resolves `authenticated`), `getToken(): string | undefined`, `login(redirectUri?)`, `logout(redirectUri?)`, `updateToken(minValiditySeconds?): Promise<boolean>`.

- [ ] **Step 1: Install** `pnpm add keycloak-js`.
- [ ] **Step 2: Create `src/shared/lib/keycloak.ts`:**

```ts
import Keycloak from 'keycloak-js';

const env = import.meta.env;
export const keycloak = new Keycloak({
  url: (env.VITE_KEYCLOAK_URL as string) || 'http://localhost:8080/auth',
  realm: (env.VITE_KEYCLOAK_REALM as string) || 'chatbotportal',
  clientId: (env.VITE_KEYCLOAK_CLIENT_ID as string) || 'portal-spa',
});

let initPromise: Promise<boolean> | null = null;

export function initKeycloak(): Promise<boolean> {
  // check-sso: does NOT force login, so guests and public pages work; login is
  // triggered on demand by ProtectedRoute / the login button.
  if (!initPromise) {
    initPromise = keycloak.init({
      onLoad: 'check-sso',
      pkceMethod: 'S256',
      silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
      checkLoginIframe: false,
    });
  }
  return initPromise;
}

export const getToken = () => keycloak.token;
export const login = (redirectUri = window.location.href) => keycloak.login({ redirectUri });
export const logout = (redirectUri = window.location.origin) => keycloak.logout({ redirectUri });
export const updateToken = (minValidity = 30) => keycloak.updateToken(minValidity);
```

- [ ] **Step 3: Add `public/silent-check-sso.html`** (a one-line file Keycloak needs for silent SSO):

```html
<html><body><script>parent.postMessage(location.href, location.origin)</script></body></html>
```

- [ ] **Step 4: Add env types** to `src/vite-env.d.ts`:

```ts
interface ImportMetaEnv {
  readonly VITE_KEYCLOAK_URL?: string;
  readonly VITE_KEYCLOAK_REALM?: string;
  readonly VITE_KEYCLOAK_CLIENT_ID?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_USE_MOCKS?: string;
}
```

- [ ] **Step 5: Document env** in the frontend `.env.example` (create if absent): `VITE_KEYCLOAK_URL=http://localhost:8080/auth`, `VITE_KEYCLOAK_REALM=chatbotportal`, `VITE_KEYCLOAK_CLIENT_ID=portal-spa`. Note it must match the backend realm and the public origin.
- [ ] **Step 6:** `pnpm build` compiles. **Commit** `feat(auth): add keycloak-js instance and env`.

### Task 2: Bearer + refresh in the axios client

**Files:** `src/shared/lib/apiClient.ts`; `src/shared/lib/apiClient.test.ts` (new).

**Interfaces:** Consumes `keycloak` (Task 1). Produces the same `api` surface, now bearer-authed.

- [ ] **Step 1: Write the failing test** (mock `@/shared/lib/keycloak`): a request attaches `Authorization: Bearer <token>` when a token exists, and omits it when undefined.

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
vi.mock('@/shared/lib/keycloak', () => ({
  keycloak: { token: 'tok123' },
  updateToken: vi.fn().mockResolvedValue(false),
}));
import { axiosInstance } from '@/shared/lib/apiClient';

it('attaches the bearer token', async () => {
  const cfg = await (axiosInstance.interceptors.request as any).handlers[0].fulfilled({ headers: {} });
  expect(cfg.headers.Authorization).toBe('Bearer tok123');
});
```

- [ ] **Step 2: Run it** → fails (no request interceptor yet).
- [ ] **Step 3: Implement.** In `apiClient.ts`: remove `withCredentials: true`; add a request interceptor that refreshes then attaches the token:

```ts
import { keycloak, updateToken } from '@/shared/lib/keycloak';

axiosInstance.interceptors.request.use(async (config) => {
  if (keycloak.authenticated) {
    try { await updateToken(30); } catch { /* refresh failed; request may 401 */ }
  }
  if (keycloak.token) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>).Authorization = `Bearer ${keycloak.token}`;
  }
  return config;
});
```

Also, in the existing response interceptor, on a 401 trigger a re-login: `if (error?.response?.status === 401 && keycloak.authenticated) keycloak.login();` (guard against loops — only when previously authenticated). Update the docstring (no more cookie).

- [ ] **Step 4:** Run the test + `pnpm test -- apiClient` → pass.
- [ ] **Step 5:** **Commit** `feat(auth): attach Keycloak bearer token to API requests`.

---

## Phase 2 — Auth context, guards, login

### Task 3: Rewrite `useAuth` for OIDC

**Files:** `src/features/auth/useAuth.tsx`; `src/features/auth/useAuth.test.tsx`.

**Interfaces:** `AuthContextType` = `{ user: AuthUser | null, isAdmin, isLoading, signOut }`. **Remove** `setAuth`, `ensureSession`, and `AuthUser.isEphemeral`.

- [ ] **Step 1: Adjust the test** (`useAuth.test.tsx`): mock `@/shared/lib/keycloak`; assert that when `keycloak.authenticated` is true the provider loads the user from `GET /api/v1/authentication/me`, and `signOut` calls `keycloak.logout`. Remove the anonymous/logout-POST assertions.
- [ ] **Step 2: Run** → fails.
- [ ] **Step 3: Implement.** `AuthProvider`:
  - On mount: if `keycloak.authenticated`, `api.get('/api/v1/authentication/me')` → `setUser`; else `setUser(null)`; then `setIsLoading(false)`.
  - `signOut` = `() => logout()`.
  - `isAdmin = user?.role === 'admin'`.
  - Delete `setAuth`, `ensureSession`, and every `isEphemeral` reference. `AuthUser` loses `isEphemeral` (backend `/me` no longer returns it — confirm the response shape: `{ id, email, displayName, role, avatarUrl }`).
- [ ] **Step 4:** `pnpm test -- useAuth` → pass.
- [ ] **Step 5:** **Commit** `refactor(auth): derive user from Keycloak session + /me`.

### Task 4: Init Keycloak at boot; guard triggers login redirect

**Files:** `src/main.tsx`, `src/features/auth/ProtectedRoute.tsx`, `src/features/auth/LoginPage.tsx`, `src/App.tsx`; their tests.

- [ ] **Step 1:** In `src/main.tsx`, `await initKeycloak()` before `ReactDOM.createRoot(...).render(...)` (keep the MSW `enableMocking()` gate; when `VITE_USE_MOCKS==='true'`, skip real init and use a mock — see Task 8). Render a lightweight splash while awaiting.
- [ ] **Step 2:** `ProtectedRoute`: when `!isLoading && !user`, call `keycloak.login({ redirectUri: window.location.href })` and render the loading skeleton (instead of `<Navigate to="/login">`). Keep the `allowedRoles`/`requireAdmin` UX checks unchanged.
- [ ] **Step 3:** `LoginPage`: replace the email/password form with a single "เข้าสู่ระบบ" button that calls `login()` (Keycloak redirect); drop the `api.post('/authentication/login')` call, `setAuth`, `PasswordInput`, and the `isEphemeral` check. Keep the branding/card. (Optionally delete the route entirely and rely on `check-sso`; keeping a `/login` landing is friendlier.)
- [ ] **Step 4:** `App.tsx`: keep `AuthProvider`; keep the `/login` route (now a redirect button). No structural route change here beyond Task 6 removals.
- [ ] **Step 5:** Update `ProtectedRoute.test.tsx`/`LoginPage.test.tsx` to the new behavior (mock `keycloak.login`). Run `pnpm test -- ProtectedRoute LoginPage` → pass.
- [ ] **Step 6:** **Commit** `feat(auth): initialize Keycloak at boot; guard redirects to Keycloak login`.

---

## Phase 3 — Endpoint moves & feature removals

### Task 5: Point chat at `/public/chat`; remove the WebSocket path

**Files:** `src/features/chat/chatApi.ts` + its caller(s) (`useChat`/ChatPage), `src/features/chat/chatApi.test.ts`.

- [ ] **Step 1:** Update the test to expect `POST /api/v1/public/chat` for the JSON and SSE paths; remove WS-path tests.
- [ ] **Step 2:** Run → fails.
- [ ] **Step 3:** In `chatApi.ts`:
  - `sendChatQuery`: `api.post('/api/v1/public/chat', request)`.
  - `streamChatSSE`: `url = ${baseUrl}/api/v1/public/chat`. Since this uses raw `fetch` (not the axios client), attach the bearer if present: `headers.Authorization = keycloak.token ? 'Bearer '+keycloak.token : undefined` (guest sends none). Refresh first if `keycloak.authenticated`.
  - **Delete** `sendChatQueryWS` entirely and switch its caller to the SSE path (the backend WebSocket is gone). Grep for `sendChatQueryWS` usages and the transport toggle (`CHAT_WS`/`useWebSocket` flag) and remove them.
- [ ] **Step 4:** `pnpm test -- chatApi chat` → pass.
- [ ] **Step 5:** **Commit** `refactor(chat): use /public/chat, drop the removed WebSocket transport`.

### Task 6: Delete the API-keys feature

**Files:** delete `src/features/api-keys/*`; modify `src/App.tsx`, `src/features/settings/SettingsLayout.tsx`, `src/features/auth/roles.ts`.

- [ ] **Step 1:** `git rm -r src/features/api-keys`.
- [ ] **Step 2:** `App.tsx`: remove the `ApiKeysPage` lazy import (L31), the `/settings/api-keys` route (L107), and the `/api-keys`→`/settings/api-keys` redirect (L115).
- [ ] **Step 3:** `SettingsLayout.tsx`: remove the `{ label: "API Keys", path: "/settings/api-keys" }` tab (L17).
- [ ] **Step 4:** `roles.ts`: remove the `/api-keys` and `/settings/api-keys` entries from `ROUTE_ROLES`; update the stale comment ("Keep in sync with the backend allowlist…") to note the backend now enforces Keycloak scopes and this map is UX-only.
- [ ] **Step 5:** `pnpm build` + `pnpm test` → green (fix any remaining import of the deleted feature).
- [ ] **Step 6:** **Commit** `chore(auth): remove the API-keys feature (backend routes deleted)`.

### Task 7: Retire the usage-by-API-key view; remove change-password

**Files:** `src/features/usage/usageApi.ts`, `src/features/usage/UsageAnalyticsPage.tsx`, `src/features/settings/SettingsLayout.tsx`; delete `src/features/auth/ChangePasswordDialog.tsx` + its trigger.

- [ ] **Step 1:** `UsageAnalyticsPage.tsx`: drop the `group_by: 'api_key'` request/tab and any rendering of `name`/`key_prefix`/`owner_email` (the backend no longer returns them). Keep `purpose`/`model`/`user` groupings. In `usageApi.ts:14` remove `'api_key'` from the `group_by` union type.
- [ ] **Step 2:** `SettingsLayout.tsx`: the "การใช้งาน API Key" tab (L18) — rename to plain usage (e.g. "การใช้งาน") since it's no longer per-key, or leave the route and just fix the label; keep the `/settings/usage` route.
- [ ] **Step 3:** Delete `ChangePasswordDialog.tsx` (passwords live in Keycloak now) and remove its trigger button (the key-icon in the sidebar user section — grep `ChangePasswordDialog`). Optionally add an "จัดการบัญชี" link to the Keycloak account console (`${VITE_KEYCLOAK_URL}/realms/${realm}/account`).
- [ ] **Step 4:** `pnpm test` + `pnpm build` → green.
- [ ] **Step 5:** **Commit** `refactor(usage): retire per-API-key usage; remove change-password (Keycloak owns it)`.

---

## Phase 4 — Mocks, logo, closeout

### Task 8: Update MSW mocks + the mock auth path

**Files:** `src/mocks/handlers.ts`, `src/main.tsx` (mock-mode init), any test setup.

- [ ] **Step 1:** In `handlers.ts`: change the chat mock from `*/api/v1/chat` to `*/api/v1/public/chat`; keep the logo POST mock but have it store `/api/v1/public/agencies/{id}/logo?v=...`; remove `/authentication/{login,logout,anonymous}` mocks; keep a `GET /authentication/me` mock returning a fake admin (so mock-mode dev has a user); remove api-keys handlers.
- [ ] **Step 2:** Mock-mode auth: when `VITE_USE_MOCKS==='true'`, `main.tsx` must NOT call real Keycloak (no Keycloak server in mock mode). Gate it: skip `initKeycloak()` and make `useAuth` treat mock mode as authenticated (e.g. a `VITE_USE_MOCKS` short-circuit in the provider, or a mock `keycloak` module via Vitest alias). Keep it simple: in `main.tsx`, `if (mocks) { /* skip init */ } else { await initKeycloak(); }`, and in `useAuth`, when mocks are on, load `/me` regardless of `keycloak.authenticated`.
- [ ] **Step 3:** `pnpm test` → green (MSW-backed tests pass against the new paths).
- [ ] **Step 4:** **Commit** `test(mocks): update MSW handlers for /public/chat and bearer auth`.

### Task 9: Verify logo rendering + full suite + build

**Files:** `src/features/agencies/useAgencies.ts`, `src/shared/components/AgencyLogo.*`; tests.

- [ ] **Step 1:** Confirm `AgencyLogo` renders `agency.logo` **as provided by the API** (the backend now returns `/api/v1/public/agencies/{id}/logo?v=...`). Update `AgencyLogo.test.tsx` fixtures to the `/public` URL. Check `useAgencies.ts:127` — if it hardcodes the old logo GET path, update to `/public`; if it's the upload POST (`/agencies/{id}/logo`, admin), leave it (upload route unchanged, and the axios client now carries the bearer).
- [ ] **Step 2:** `pnpm test` (full) → green; `pnpm build` → succeeds; `pnpm lint` → clean.
- [ ] **Step 3:** **Commit** `test(agency): logo served under /public`.

### Task 10: Realm redirect URIs + end-to-end smoke + docs

**Files:** `deploy/keycloak/realm-export.json` (redirect URIs / web origins), `.env.example`, `CONTEXT.md`.

- [ ] **Step 1:** In `realm-export.json`, set the `portal-spa` client's `redirectUris` and `webOrigins` to the SPA origin(s): dev `http://localhost:8080/*` (the Caddy gateway port) and `http://localhost:5173/*` (Vite dev server) and the silent-sso URL; prod `https://<domain>/*`. `webOrigins` includes those origins (or `+`).
- [ ] **Step 2:** E2E smoke (compose up): load the SPA at the gateway origin, click login → Keycloak `/auth` login → redirect back authenticated; confirm an admin page loads (bearer accepted), guest chat works logged-out at `/public/chat`, and logout redirects to Keycloak. (The backend + Keycloak are already verified working behind Caddy.)
- [ ] **Step 3:** Update `CONTEXT.md`: flip the "frontend NOT yet migrated" note to "migrated 2026-08-19 — Keycloak OIDC (keycloak-js), bearer, /public/chat"; refresh the frontend/auth section.
- [ ] **Step 4:** **Commit** `docs/deploy: SPA OIDC redirect URIs; mark frontend Keycloak migration done`.

---

## Self-review notes

- **Contract coverage:** bearer transport (T2), OIDC session (T1,T3,T4), guest-open public pages (`check-sso`, T1/T4), moved chat URL + WS removal (T5), api-keys removal (T6), usage-by-key + change-password removal (T7), logo `/public` (T9), redirect URIs (T10). All frontend-handoff items covered.
- **Guest chat stays open:** `onLoad: 'check-sso'` never forces login, and `/public/chat` needs no token — a guest can chat; a logged-in user's token is attached when present.
- **Security note:** client-side role gating is UX-only; the backend's per-route scopes are the real control (route-audit proven). Never gate sensitive data on `ProtectedRoute` alone.
- **Type consistency:** `AuthUser` drops `isEphemeral`; `getToken`/`login`/`logout`/`updateToken`/`keycloak` are the single auth surface used by `apiClient`, `useAuth`, `ProtectedRoute`, `LoginPage`, and `chatApi`.
