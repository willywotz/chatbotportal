# Anonymous Sessions + WS-Default Chat — Phase C & D Design

**Date:** 2026-07-27
**Status:** Approved (brainstorming), pending implementation plan
**Branch:** `feat/chat-ws-default` (off `dev`)
**Epic:** Cookie-session auth. Phase A (session cookie, JWT removed) is merged. This
covers **Phase C** (anonymous `/chat` session) and **Phase D** (WebSocket cookie auth +
making WS the browser chat default — the original goal). Built together because a
WS-first anonymous user needs a session cookie before the handshake.

## 1. Goal

- **Phase C:** anonymous public-portal visitors get a persistent session so their `/chat`
  history survives reloads, without reopening the OpenAI-compatible surfaces to
  auto-created identities.
- **Phase D:** the `/chat` and `/responses` WebSocket handlers authenticate via the
  auto-attached session cookie (same-origin), and the browser chat defaults to WebSocket
  with SSE→JSON fallback.

## 2. Phase C — anonymous session

### 2.1 `POST /auth/anon` (bootstrap)
New endpoint (`app/routers/auth.py`):
- If the request already carries a session cookie that resolves to a user → return that
  user, set nothing (idempotent).
- Else create an anonymous user: `User(email=f"anon-{uuid}@ephemeral.local",
  is_ephemeral=True, role="user", hashed_password=<unusable>)`, `create_session(user.id)`,
  set the session cookie (same attributes as login), return `{ "user": {…} }`.
- Anonymous users are created **only when someone actually chats** (the frontend calls
  this right before the first turn when there is no session) — not per page-load.

### 2.2 Anonymous identity
- Reuses the existing `User.is_ephemeral` flag (already in the model; already excluded
  from the admin user list). Role `"user"` → the role allowlist grants chat + own-history
  (`enforce_role_allowlist` maps unknown/`user` → basic-user permissions).
- `Conversation.user` is nullable, but anon turns are owned by the anon user row so
  history is scoped by session → user id (same as an authenticated user).

### 2.3 OpenAI surfaces reject anonymous
Phase A made `/responses` + `/conversations` require `get_current_user`. Phase C adds:
those surfaces must reject `is_ephemeral` users (anon sessions are for `/chat`, not the
machine APIs). New dependency `get_current_user_non_ephemeral` (wraps `get_current_user`;
401 if `user.is_ephemeral`) used in `responses.py` + `openai_conversations.py`. An API key
(never ephemeral) and a real logged-in user both pass; an anon session gets 401.

### 2.4 Anon-user growth (noted, minimal handling)
Anon `User` rows persist after their Redis session expires (TTL). Unbounded growth is a
real concern but a full prune job is **out of scope** for this phase; documented as
follow-up. (Mitigation already in place: anon rows are created only on first chat, not per
visit, and are hidden from the admin list.)

## 3. Phase D — WebSocket cookie auth + WS-default

### 3.1 WS caller resolution (both `/chat` and `/responses`)
- `app/services/chat/ws.py::bearer_user` and `app/routers/responses.py::_ws_user` gain
  cookie resolution: **same precedence as HTTP** — `Authorization: Bearer` header present
  → API-key only; else `websocket.cookies.get(SESSION_COOKIE_NAME)` → `resolve_session` →
  `User`. Browsers auto-send the cookie on the same-origin handshake.
- `/responses` WS additionally **requires a non-ephemeral authenticated user** (consistent
  with `/responses` HTTP): if resolution yields `None` or an `is_ephemeral` user, close the
  socket with a policy-violation code instead of running anonymously. This closes the
  anonymous `/responses` WS gap flagged in Phase A review. `/chat` WS accepts anon sessions
  (anon chat is allowed).

### 3.2 WS Origin check (CSWSH defense — required)
Because the cookie now authenticates WebSockets, add a cross-site-WebSocket-hijacking
guard: both WS handlers validate the handshake `Origin` header against the allowed origins
(`settings.CORS_ORIGINS`); a disallowed/missing Origin → close with code 1008 before
`accept()`. `SameSite=Lax` already stops the cookie riding a cross-site WS handshake; the
Origin check is defense-in-depth and the standard WS protection. (A shared helper reads
`CORS_ORIGINS`; wildcard `"*"` — dev only — allows all.)

### 3.3 Frontend: WS-first with SSE→JSON fallback
- New `sendChatQueryWS(request, callbacks, signal)` in `chatApi.ts`: opens
  `new WebSocket(<wsBase>/api/v1/chat)` (derive `ws://`/`wss://` from the API base /
  `window.location`), on open sends `{query, conversation_id?, model?}`, dispatches each
  `{event, data}` frame to the SAME `SSECallbacks`, resolves `true` on the terminal `done`
  frame. **Fallback rule (avoids double-running a turn):** return `false` (→ fall back to
  SSE) ONLY when the socket never opened or closed **before the first frame** — i.e. the
  turn provably never started upstream. If frames already arrived and then the socket dies
  before `done`, emit `onError` and return `true` (WS was used; do NOT re-run over SSE, or
  the turn persists twice).
- `useChatStream.startStream` tries WS first; on `false` falls back to `sendChatQuerySSE`
  (existing), which itself falls back to JSON (`sendChatQuery`) — WS→SSE→JSON.
- **Anon bootstrap before the socket:** before the first turn, if `useAuth.user` is null
  (anonymous, no session), `await api.post('/auth/anon')` to mint the session cookie, then
  open the WS (which now carries it). Authenticated / already-anon users skip it. Add
  `ensureSession()` to the auth context (POST `/auth/anon`, store the returned user) and
  call it from the chat send path. Idempotent, so repeated calls are safe.

## 4. Security considerations

- **CSWSH:** `SameSite=Lax` + the Origin check (§3.2). Both WS endpoints validate Origin.
- **Anon abuse:** anon sessions are low-privilege `is_ephemeral` users; the role allowlist
  keeps them to chat + own history; they cannot reach admin/staff/ops or the OpenAI APIs.
- **Rate limiting:** anon `/auth/anon` + `/chat` are subject to the existing limiters;
  no new unauthenticated write beyond the (idempotent) session bootstrap.
- **No new client-readable state:** the anon session is the same HttpOnly cookie; nothing
  is stored in JS.

## 5. Breaking changes

- `/responses` + `/conversations` (HTTP already required auth in Phase A) now also reject
  `is_ephemeral` sessions — an anon browser session cannot call them (by design).
- `/responses` WebSocket now requires a non-anon authenticated caller (was anonymous-ok).
- Browser chat default transport becomes WebSocket (SSE remains as automatic fallback, so
  no user-visible regression when WS is blocked).

## 6. Testing

**Phase C:**
- `POST /auth/anon`: no cookie → creates an `is_ephemeral` user + sets the session cookie;
  with an existing valid session → idempotent (same user, no new row).
- An anon session authenticates `/chat` (turn persists under the anon user; history scoped
  to it).
- `/responses` + `/conversations` with an anon session → 401; with an API key → 200;
  with a real user session → 200.
- `get_current_user_non_ephemeral`: ephemeral user → 401; real user / API key → passes.

**Phase D:**
- `/chat` WS authenticates via a session cookie (no header); anon session cookie works;
  API-key header still works.
- `/responses` WS: real user/API-key cookie → runs; anon/None → closed (policy code).
- Origin check: allowed Origin → accepted; disallowed/missing → closed 1008 (both WS).
- Frontend: `sendChatQueryWS` happy path dispatches events + resolves on `done`; connect
  failure → returns false; `startStream` falls back WS→SSE→JSON; `ensureSession` posts
  `/auth/anon` only when `user` is null and is idempotent.

## 7. Out of scope

- Anon-user prune/cleanup job (documented follow-up).
- Multi-turn-over-one-socket UX changes (the WS still runs one turn per frame as today).
- Changing SSE/JSON behavior beyond adding WS in front.

## 8. Risks

- **WS Origin/cookie nuances** across the nginx/Cloudflare hops — the handshake must
  preserve `Origin` and `Cookie`; verified against `nginx/routes.conf` (same-origin) in
  the plan.
- **Fallback correctness / no double-turn:** fall back to SSE only when the WS closed
  before its first frame (turn never started); a mid-stream death after frames arrived is
  surfaced as an error, never silently re-run over SSE (which would persist the turn twice).
- **Anon growth** until a prune exists (accepted, documented).
