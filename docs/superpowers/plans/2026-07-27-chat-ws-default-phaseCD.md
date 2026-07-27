# Anonymous Sessions + WS-Default Chat — Phase C & D Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give anonymous visitors a persistent `/chat` session (Phase C) and make the browser chat default to WebSocket with SSE→JSON fallback, with WS authenticating via the session cookie (Phase D).

**Architecture:** `POST /auth/anon` mints an `is_ephemeral` user + session cookie on first chat. The OpenAI surfaces reject ephemeral sessions. Both WS handlers resolve the caller from header API-key or the session cookie (same precedence as HTTP) behind an Origin check (CSWSH). The frontend tries WS first (`sendChatQueryWS`), falling back to SSE then JSON, and bootstraps an anon session before opening the socket.

**Tech Stack:** Python 3.12, FastAPI/Starlette, Tortoise ORM, pytest; React + TS, Vitest + MSW.

## Global Constraints

- TDD mandatory; Google style; imports sorted by path; American English.
- `.venv/bin/pytest <path>` from `backend/` (NOT `rtk pytest`). Frontend `rtk vitest run <path>` from `frontend/`.
- Orchestrator owns git/commits/context.md; builders do NOT commit.
- Anon user: `User(email=f"anon-{uuid4().hex}@ephemeral.local", is_ephemeral=True, role="user", hashed_password=UNUSABLE_PASSWORD)` where `UNUSABLE_PASSWORD = "!"` (never verified; anon never logs in).
- WS precedence mirrors HTTP: `Authorization: Bearer` present → API-key only (no cookie fallback); else session cookie.
- `/responses` (HTTP + WS) + `/conversations` reject `is_ephemeral`; `/chat` accepts anon.
- WS fallback rule: fall back to SSE ONLY if the socket closed before its first frame; a post-first-frame death → `onError`, no re-run (avoids double-persisting a turn).
- Session cookie name/attrs from Phase A (`settings.SESSION_COOKIE_NAME`, `AUTH_COOKIE_SECURE`).
- Spec: `docs/superpowers/specs/2026-07-27-chat-ws-default-phaseCD-design.md`.
- Branch: `feat/chat-ws-default` (already created off `dev`).

## File Structure

**Create:** `backend/app/auth/ws.py` (shared WS auth+origin), `backend/tests/routers/test_auth_anon.py`, `backend/tests/auth/test_ws_auth.py`, `frontend/src/features/chat/chatWs.ts` (or extend `chatApi.ts`), test files.
**Modify:** `backend/app/routers/auth.py`, `backend/app/auth/dependencies.py` (non-ephemeral dep), `backend/app/routers/responses.py`, `backend/app/routers/openai_conversations.py`, `backend/app/services/chat/ws.py`, `backend/tests/routers/test_openai_requires_auth.py`, `backend/tests/routers/test_chat_ws.py`; frontend `chatApi.ts`, `useChatStream.ts`, `useChat.ts`, `features/auth/useAuth.tsx`, `features/auth/LoginPage.tsx`.

**Order:** C1 → C2 → D1 → D2 → D3 → Integration.

---

## Task C1: `POST /auth/anon` + isEphemeral in user dict

**Files:** Modify `backend/app/routers/auth.py`; Test: `backend/tests/routers/test_auth_anon.py`

**Interfaces — Produces:** `POST /auth/anon` (idempotent anon-session bootstrap); `_user_dict` gains `"isEphemeral"`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/routers/test_auth_anon.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.models.user import User
from app.routers import auth as auth_router


def _app():
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_anon_creates_ephemeral_user_and_cookie(db):
    client = TestClient(_app())
    r = client.post("/api/v1/auth/anon")
    assert r.status_code == 200
    body = r.json()["user"]
    assert body["isEphemeral"] is True
    assert settings.SESSION_COOKIE_NAME in r.headers.get("set-cookie", "")
    u = await User.get(id=body["id"])
    assert u.is_ephemeral is True and u.role == "user"


@pytest.mark.asyncio
async def test_anon_is_idempotent_with_existing_session(db):
    client = TestClient(_app())
    r1 = client.post("/api/v1/auth/anon")           # TestClient persists the cookie
    first_id = r1.json()["user"]["id"]
    before = await User.filter(is_ephemeral=True).count()
    r2 = client.post("/api/v1/auth/anon")
    assert r2.json()["user"]["id"] == first_id
    assert await User.filter(is_ephemeral=True).count() == before  # no new row
```

- [ ] **Step 2: Run — expect FAIL.** `cd backend && .venv/bin/pytest tests/routers/test_auth_anon.py -v`

- [ ] **Step 3: Implement** — in `auth.py`:
- Add `"isEphemeral": user.is_ephemeral` to `_user_dict`.
- Add the endpoint (imports: `create_session` already there; `Request`, `Response`, `settings` already there from Phase A; `from app.auth.security import hash_password`? no — use the sentinel):

```python
_UNUSABLE_PASSWORD = "!"  # anon users never authenticate with a password


@router.post("/anon", summary="Start an anonymous session (idempotent)")
async def anon(request: Request, response: Response) -> dict:
    sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        from app.services.auth_session import resolve_session
        user_id = await resolve_session(sid)
        if user_id:
            user = await User.filter(id=user_id, is_active=True).first()
            if user:
                return {"user": _user_dict(user)}
    user = await User.create(
        email=f"anon-{uuid4().hex}@ephemeral.local",
        is_ephemeral=True, role="user", hashed_password=_UNUSABLE_PASSWORD,
    )
    session_id = await create_session(str(user.id))
    response.set_cookie(
        settings.SESSION_COOKIE_NAME, session_id, httponly=True,
        secure=settings.AUTH_COOKIE_SECURE, samesite="Lax",
        max_age=settings.SESSION_TTL_MINUTES * 60, path="/",
    )
    return {"user": _user_dict(user)}
```

Add `from uuid import uuid4` at the top.

- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** — `feat: POST /auth/anon anonymous session bootstrap`

---

## Task C2: reject ephemeral sessions on the OpenAI surfaces

**Files:** Modify `backend/app/auth/dependencies.py`, `backend/app/routers/responses.py`, `backend/app/routers/openai_conversations.py`; Test: update `backend/tests/routers/test_openai_requires_auth.py`.

**Interfaces — Produces:** `get_current_user_non_ephemeral(user=Depends(get_current_user)) -> User` (401 if `user.is_ephemeral`).

- [ ] **Step 1: Failing test** — add to `test_openai_requires_auth.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from app.config import settings
from app.models.user import User


@pytest.mark.asyncio
async def test_responses_rejects_anonymous_session(db):
    anon = await User.create(email="anon-x@ephemeral.local", is_ephemeral=True,
                             role="user", hashed_password="!", is_active=True)
    with patch("app.auth.dependencies.resolve_session", new=AsyncMock(return_value=str(anon.id))):
        with TestClient(_client_app()) as client:
            r = client.post("/api/v1/responses", json={"model": "onechat", "input": "hi"},
                            cookies={settings.SESSION_COOKIE_NAME: "anon-sid"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run — expect FAIL** (anon currently authenticates). `.venv/bin/pytest tests/routers/test_openai_requires_auth.py -v`

- [ ] **Step 3: Implement**
- `dependencies.py`, after `get_current_user`:

```python
async def get_current_user_non_ephemeral(
    user: User = Depends(get_current_user),
) -> User:
    """Real accounts / API keys only — anonymous (ephemeral) sessions are refused.

    The OpenAI-compatible surfaces are not for auto-created anonymous identities.
    """
    if user.is_ephemeral:
        raise _invalid_credentials
    return user
```

- `responses.py` + `openai_conversations.py`: replace `Depends(get_current_user)` with `Depends(get_current_user_non_ephemeral)` on every data endpoint (import it). (Grep both files for `get_current_user` to catch all sites.)

- [ ] **Step 4: Run — expect PASS**, then re-run the OpenAI suites (`test_openai_conversations`, `test_openai_items`, `test_responses_*`) and confirm still green (real-user/API-key tests unaffected).
- [ ] **Step 5: Commit** — `feat: reject ephemeral sessions on /responses + /conversations`

---

## Task D1: WS cookie auth + Origin check (both `/chat` and `/responses`)

**Files:** Create `backend/app/auth/ws.py`; Modify `backend/app/services/chat/ws.py`, `backend/app/routers/responses.py`; Test: `backend/tests/auth/test_ws_auth.py`, update `backend/tests/routers/test_chat_ws.py`, `test_responses_ws_route.py`.

**Interfaces — Produces (in `app/auth/ws.py`):** `async resolve_ws_user(websocket) -> User | None`; `ws_origin_allowed(websocket) -> bool`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/auth/test_ws_auth.py
from unittest.mock import AsyncMock, patch
import pytest
from app.auth.ws import resolve_ws_user, ws_origin_allowed
from app.config import settings
from app.models.user import User


class _WS:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}


def test_origin_allowed_matches_cors(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://ok.example"])
    assert ws_origin_allowed(_WS(headers={"origin": "https://ok.example"})) is True
    assert ws_origin_allowed(_WS(headers={"origin": "https://evil.example"})) is False
    assert ws_origin_allowed(_WS()) is False  # missing origin


def test_origin_wildcard_allows_all(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["*"])
    assert ws_origin_allowed(_WS(headers={"origin": "https://anything"})) is True


@pytest.mark.asyncio
async def test_resolve_ws_user_from_cookie(db):
    u = await User.create(email="a@b.co", hashed_password="x", role="user", is_active=True)
    with patch("app.auth.ws.resolve_session", new=AsyncMock(return_value=str(u.id))):
        got = await resolve_ws_user(_WS(cookies={settings.SESSION_COOKIE_NAME: "sid"}))
    assert got.id == u.id


@pytest.mark.asyncio
async def test_resolve_ws_user_bad_header_no_cookie_fallback(db):
    # header present but not a valid api-key -> None, cookie ignored
    with patch("app.auth.ws.resolve_session", new=AsyncMock(return_value="should-not-be-used")):
        got = await resolve_ws_user(_WS(headers={"authorization": "Bearer tcg_bad"},
                                        cookies={settings.SESSION_COOKIE_NAME: "sid"}))
    assert got is None
```

- [ ] **Step 2: Run — expect FAIL.** `.venv/bin/pytest tests/auth/test_ws_auth.py -v`

- [ ] **Step 3: Implement `app/auth/ws.py`**

```python
# backend/app/auth/ws.py
"""WebSocket caller resolution + Origin check.

Same precedence as the HTTP path (header API-key decides; else session cookie).
The Origin check is the standard cross-site-WebSocket-hijacking defense — cookies
now authenticate sockets, so a browser page from another origin must not be able
to open an authenticated socket (SameSite=Lax already blocks the cookie; this is
defense-in-depth).
"""
from app.auth.dependencies import _resolve_api_key
from app.config import settings
from app.models.user import User
from app.services.auth_session import resolve_session


async def resolve_ws_user(websocket) -> User | None:
    auth = websocket.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return await _resolve_api_key(auth[7:])          # header decides
    sid = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        user_id = await resolve_session(sid)
        if user_id:
            return await User.filter(id=user_id, is_active=True).first()
    return None


def ws_origin_allowed(websocket) -> bool:
    allowed = settings.CORS_ORIGINS
    if "*" in allowed:
        return True
    return websocket.headers.get("origin") in allowed
```

- [ ] **Step 4: Wire into `/chat` WS** (`app/services/chat/ws.py` + `app/routers/chat.py`): replace `bearer_user` usage with `resolve_ws_user`; in `chat_ws` (chat.py) add the origin gate FIRST:

```python
# chat.py chat_ws, at the very top of the handler:
    from app.auth.ws import ws_origin_allowed
    if not ws_origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    # ...then the existing _connections.acquire() / accept() / resolve user
```

Change `ws.py`'s `handle_chat_frame` caller so the user is resolved via `resolve_ws_user` (import from `app.auth.ws`); delete the now-unused `bearer_user` in `ws.py` (or re-export for compatibility if a test imports it — grep `bearer_user` in tests and update).

- [ ] **Step 5: Wire into `/responses` WS** (`responses.py` `responses_websocket`): add the origin gate first; resolve via `resolve_ws_user`; **require non-anon**:

```python
    from app.auth.ws import resolve_ws_user, ws_origin_allowed
    if not ws_origin_allowed(websocket):
        await websocket.close(code=1008); return
    if not _connections.acquire():
        await websocket.close(code=1013); return
    try:
        await websocket.accept()
        user = await resolve_ws_user(websocket)
        if user is None or user.is_ephemeral:
            await send(_error_frame(ResponsesApiError(
                "Authentication required.", type="invalid_request_error", status=401)))
            await websocket.close(code=1008); return
        session = WsSession(user=user)
        ...
```

Remove/replace the old `_ws_user`.

- [ ] **Step 6: Update WS tests** — `test_chat_ws.py`: existing tests connect without an Origin header; add an allowed Origin (or set `CORS_ORIGINS=["*"]` in the test app fixture) so they still pass, and add: (a) a cookie-authenticated `/chat` WS round-trip; (b) a disallowed-Origin connection is refused. `test_responses_ws_route.py`: add an allowed Origin; add a test that an anon/None caller is closed, and a real user/API-key caller runs. Mirror the header-setting approach `TestClient.websocket_connect(url, headers={"origin": ...})`.

- [ ] **Step 7: Run** — `.venv/bin/pytest tests/auth/test_ws_auth.py tests/routers/test_chat_ws.py tests/routers/test_responses_ws_route.py -q` green; `.venv/bin/python -c "import app.main"`.
- [ ] **Step 8: Commit** — `feat: WS cookie auth + Origin check on /chat and /responses`

---

## Task D2: frontend `sendChatQueryWS` + fallback rule

**Files:** Modify `frontend/src/features/chat/chatApi.ts`; Test: `frontend/src/features/chat/chatApi.test.ts` (or a new `chatWs.test.ts`).

**Interfaces — Produces:** `sendChatQueryWS(request, callbacks, signal?) => Promise<boolean>`; extract a shared `dispatchStreamEvent(event, data, callbacks)` used by both SSE and WS.

- [ ] **Step 1: Failing test** — with a mocked `WebSocket` (a small fake that lets the test drive `onopen`/`onmessage`/`onclose`), assert: on `open` it sends the request JSON; each `{event,data}` frame calls the matching callback; a `done` frame resolves `true`; a `close` before any frame resolves `false`; a `close` after frames resolves `true` (no fallback).

- [ ] **Step 2: Run — expect FAIL.** `cd frontend && rtk vitest run src/features/chat/chatApi.test.ts`

- [ ] **Step 3: Implement** — extract the SSE `dispatch` switch into `dispatchStreamEvent(event: string, data: unknown, cb: SSECallbacks)`; have the SSE path call it. Add:

```ts
export async function sendChatQueryWS(
  request: ChatApiRequest, callbacks: SSECallbacks, signal?: AbortSignal,
): Promise<boolean> {
  const httpBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) || window.location.origin;
  const url = `${httpBase.replace(/^http/, 'ws')}/api/v1/chat`;
  return new Promise<boolean>((resolve) => {
    let ws: WebSocket;
    try { ws = new WebSocket(url); } catch { resolve(false); return; }
    let receivedFrame = false;
    let settled = false;
    const finish = (v: boolean) => {
      if (settled) return; settled = true;
      try { ws.close(); } catch { /* noop */ }
      resolve(v);
    };
    signal?.addEventListener('abort', () => finish(receivedFrame));
    ws.onopen = () => ws.send(JSON.stringify(request));
    ws.onmessage = (ev) => {
      receivedFrame = true;
      let frame: { event?: string; data?: unknown };
      try { frame = JSON.parse(ev.data as string); } catch { return; }
      if (frame.event) dispatchStreamEvent(frame.event, frame.data, callbacks);
      if (frame.event === 'done') finish(true);
    };
    ws.onerror = () => { if (!receivedFrame) finish(false); };   // pre-frame error -> fall back
    ws.onclose = () => finish(receivedFrame);                    // closed before frame -> false
  });
}
```

- [ ] **Step 4: Run — expect PASS** + `./node_modules/.bin/tsc --noEmit` clean.
- [ ] **Step 5: Commit** — `feat(fe): WebSocket chat client with SSE fallback rule`

---

## Task D3: frontend WS-first + anon bootstrap

**Files:** Modify `frontend/src/features/chat/useChatStream.ts`, `frontend/src/features/chat/useChat.ts`, `frontend/src/features/auth/useAuth.tsx`, `frontend/src/features/auth/LoginPage.tsx`; update their tests.

**Interfaces — Produces:** `useAuth().ensureSession(): Promise<void>`; `AuthUser.isEphemeral: boolean`; `startStream` tries WS then SSE.

- [ ] **Step 1: Failing tests** — `useAuth.test.tsx`: `ensureSession` POSTs `/api/v1/auth/anon` and sets the user when `user` is null, and is a no-op when a user exists. `useChatStream`: `startStream` calls `sendChatQueryWS` first and only calls `sendChatQuerySSE` when WS returns false. `LoginPage.test.tsx`: an `isEphemeral` user does NOT trigger the redirect-to-/chat.

- [ ] **Step 2: Run — expect FAIL.** `cd frontend && rtk vitest run src/features/auth src/features/chat/useChatStream.test.tsx`

- [ ] **Step 3: Implement**
- `useAuth.tsx`: add `isEphemeral: boolean` to `AuthUser`; add to context `ensureSession`:

```ts
const ensureSession = useCallback(async () => {
  if (user) return;
  try {
    const res = await api.post<{ user: AuthUser }>('/api/v1/auth/anon', {});
    setUser(res.user);
  } catch { /* proceed; chat may 401 and surface an error */ }
}, [user]);
```
  Expose `ensureSession` on the context type + provider value.
- `LoginPage.tsx`: guard the redirect so anon users can still log in: `if (!isLoading && user && !user.isEphemeral) navigate('/chat')` (both the effect and the early `return null`).
- `useChatStream.ts`: in `startStream`, try WS first, fall back to SSE:

```ts
    const { sendChatQueryWS } = await import('@/features/chat/chatApi');
    const usedWS = await sendChatQueryWS(request, callbacks, abortController.signal);
    const usedStream = usedWS || await sendChatQuerySSE(request, callbacks, abortController.signal);
    if (abortController.signal.aborted) return { usedSSE: usedStream, aborted: true };
    return { usedSSE: usedStream, aborted: false };
```
  (Keep the `usedSSE` field name — it now means "a stream (WS or SSE) handled it"; `useChat` already treats it as "streaming happened, skip JSON".)
- `useChat.ts`: before `startStream`, `await ensureSession()` (pull it from `useAuth()`), so an anonymous first turn has a session cookie before the socket opens.

- [ ] **Step 4: Run — expect PASS** + `./node_modules/.bin/tsc --noEmit` clean.
- [ ] **Step 5: Commit** — `feat(fe): WS-first chat with anon-session bootstrap`

---

## Task Integration: parity, suites, context.md

**Files:** `backend/tests/test_surface_parity.py`, `context.md`.

- [ ] **Step 1:** add `("POST", "/api/v1/auth/anon")` to surface parity; `.venv/bin/pytest tests/test_surface_parity.py -v`.
- [ ] **Step 2:** full backend `.venv/bin/pytest -q` green.
- [ ] **Step 3:** full frontend `rtk vitest run` green; `tsc --noEmit` clean.
- [ ] **Step 4:** manual smoke (per `/run`): anon visitor → first chat triggers `/auth/anon` (cookie set) → WS turn works; reload → history persists via `/auth/me`; `/responses` with anon session → 401; disallowed-Origin WS → refused.
- [ ] **Step 5:** update `context.md`: anon `/chat` session via `POST /auth/anon` (`is_ephemeral` user, created on first chat); OpenAI surfaces reject ephemeral (`get_current_user_non_ephemeral`); WS (`/chat` + `/responses`) authenticate via cookie behind an Origin check (`app/auth/ws.py`); browser chat is WS-first (SSE→JSON fallback) with `ensureSession` bootstrap; `AuthUser.isEphemeral`.
- [ ] **Step 6: Commit** — `docs: update context.md for anon sessions + WS-default chat`

---

## Self-Review

**Spec coverage:** anon bootstrap (C1), ephemeral gating on OpenAI surfaces (C2), WS cookie auth + Origin check on both sockets (D1), WS client + no-double-turn fallback (D2), WS-first + anon bootstrap + login guard (D3), parity/suites/context (Integration). ✓
**Placeholder scan:** all steps carry real code; the grep-and-fix sweeps (C2 all `get_current_user` sites, D1 `bearer_user` in tests) are explicit. ✓
**Type/name consistency:** `resolve_ws_user`/`ws_origin_allowed`, `get_current_user_non_ephemeral`, `sendChatQueryWS`/`dispatchStreamEvent`, `ensureSession`, `AuthUser.isEphemeral`, `_UNUSABLE_PASSWORD` used consistently across producing/consuming tasks. ✓
**Cross-task risk:** D1 changes both WS handlers' auth — the WS tests (D1 Step 6) must set an allowed Origin or they'll be refused by the new gate; called out. `_resolve_api_key` is imported by `app/auth/ws.py` from `dependencies.py` — no cycle (dependencies doesn't import ws).
