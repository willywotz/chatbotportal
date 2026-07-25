# Responses API — OneChat Version Selection

**Date:** 2026-07-25
**Branch:** `feat/responses-onechat-versions`
**Status:** Approved for planning

## 1. Purpose

Let the OpenAI-compatible Responses API reach **every** OneChat upstream
(`/v1`–`/v5`), on both transports (HTTP + WebSocket), and stop leaking OneChat's
versioning into the public model name.

Today `run_response()` only reaches v4/v5: `resolve_model()` maps a handful of
`thai-citizen-guide[-vN]` model ids to a pinned stream version, and
`run_turn → _stream_live` calls `client.stream_by_version()`, which only knows
the two SSE endpoints. v1/v2/v3 are non-streaming (`/vN/chat` returns one JSON
envelope) and are unreachable from the Responses path.

This spec:

1. Renames the single public model id to **`onechat`** (hard rename — the old
   `thai-citizen-guide[-vN]` ids are removed).
2. Moves version selection **out** of the Responses layer. The model id no
   longer carries a version.
3. Adds a **per-request** version override, delivered as a request-body field so
   it works identically on HTTP and WebSocket.
4. **Removes** the `CHAT_STREAM_VERSION` setting entirely.
5. Teaches the OneChat client to serve v1/v2/v3 as a uniform event stream, by
   adapting their single JSON envelope into `answer` + `done` events.

**Out of scope:** the standalone onechat service; the portal `/chat/stream`
route's *frontend* (it keeps working, see §6); `/v1/mcp/*`.

## 2. Version Resolution

One resolver owns the whole policy. It lives in the OneChat client module
(`services/onechat/client.py`) — the "client level" home for version logic.

```python
NEWEST_VERSION = "v5"
_VALID = {"v1", "v2", "v3", "v4", "v5"}

def resolve_version(requested: str | None = None) -> str:
    v = (requested or "").strip().lower()
    return v if v in _VALID else NEWEST_VERSION
```

**Precedence (two tiers):**

1. **Per-request override** — the caller names a version for this request.
2. **Newest** — `NEWEST_VERSION` (v5) when no valid override is given.

There is no config-level pin. `CHAT_STREAM_VERSION` is deleted. An unknown or
malformed override silently resolves to newest (matching the previous
unknown-value behavior); no 400 for a bad version — it is best-effort.

## 3. Public model id

- Canonical id: **`onechat`**. It is the only accepted value.
- `resolve_model(model)` returns the id and raises `ResponsesApiError`
  (400, `invalid_request_error`, `param="model"`) for anything else.
- **Hard rename:** `thai-citizen-guide`, `thai-citizen-guide-v4`,
  `thai-citizen-guide-v5` are removed. A client sending them gets a 400.
- The model id never encodes a version.

## 4. Per-request override channel

The override is a **request-body field**, not a header. Rationale: browsers
cannot set headers on a WebSocket (the code already relies on this —
`responses.py` `_ws_user`), and both transports validate the same
`ResponsesRequest`. A body field is the only channel that works uniformly.

```python
# schemas/responses.py — extra="ignore" already lets SDK clients pass it via extra_body
onechat_version: str | None = None
```

Clients send `extra_body={"onechat_version": "v3"}` (OpenAI SDK) or a plain JSON
field. Absent/invalid → newest.

## 5. Serving v1/v2/v3 as events

v4/v5 stream SSE; v1/v2/v3 return a single JSON envelope. `spec/api/v3.md` §9
states v3's `data.sections` / `data.debug` equals v4/v5's `answer` event
payload. So the adapter unwraps `data` and emits two synthetic events:

```python
class OneChatClient:
    def __init__(self, ..., version: str | None = None):
        self.version = version or resolve_version()

    async def events(self, query, mcp_endpoint_url, session_id=None):
        v = self.version
        if v in ("v4", "v5"):
            async for ev in self._stream(f"/{v}/chat", query, mcp_endpoint_url, session_id):
                yield ev
            return
        env = await self._post_json(f"/{v}/chat", query, mcp_endpoint_url, session_id)
        data = env.get("data", env)
        yield ("answer", data)
        yield ("done", {
            "session_id": data.get("session_id"),
            "total_ms": (data.get("debug") or {}).get("responseTimeMs"),
        })

def get_client(version: str | None = None) -> OneChatClient:
    return OneChatClient(version=version or resolve_version())
```

The `ResponseAccumulator` only reacts to `answer`, `done`, `error`
(`translate.py`), so both transports and all five versions drive one accumulator
unchanged. `_post_json` already raises `OneChatError(504/502)`, which
`_stream_live`'s existing `except OneChatError` turns into `error` + `done`
events — so error mapping for the sync versions is free.

`stream_by_version` is **replaced** by `events()`.

## 6. Flow & the portal route

```
ResponsesRequest.onechat_version
  → run_response(): resolve_model(model) validates "onechat"
  → prepare_turn(requested_version=body.onechat_version)
       plan.stream_version = resolve_version(requested_version)
  → _stream_live(): get_client(plan.stream_version).events(...)
```

`plan.stream_version` is the concrete resolved version and continues to feed the
`ConnectionLog` (`connection_type=f"external_chat_{version}"`) and the
accumulator's reported `portal.stream_version`.

**Portal `/chat/stream` consequence (accepted):** that route also calls
`prepare_turn`, previously choosing its upstream via `CHAT_STREAM_VERSION`. With
the setting gone and no per-request override on that route, **the portal always
uses newest (v5)**. This removes the no-redeploy rollback lever
(`set CHAT_STREAM_VERSION=v4` at `/settings`) that the v4→v5 migration used.
This is an accepted tradeoff: v5 is settled. If portal-side version control is
needed later, it returns as a per-request param on `/chat/stream`, not a global
setting.

## 7. Removing `CHAT_STREAM_VERSION`

Deleted from: `config.py` (setting + `SETTINGS_GROUPS["OneChat"]`),
`.env.prod.example`. `_stream_version()` in `chat/stream.py` becomes a thin
`resolve_version()` wrapper (preserving the `chat.py` re-export that
`test_chat_stream_version.py` imports — though that test is deleted, other code
imports the name).

## 8. Blast radius

**Code:** `schemas/responses.py`, `services/responses/request.py`,
`routers/responses.py`, `services/onechat/client.py`, `services/chat/stream.py`,
`services/responses/retrieve.py`, `config.py`, `.env.prod.example`.

**Tests:** rename `thai-citizen-guide` → `onechat` across
`test_responses_http.py`, `test_responses_ws_route.py`,
`test_responses_ws_session.py`, `test_responses_translate.py`,
`test_responses_stubs.py`; rewrite `test_responses_request.py`; delete
`test_chat_stream_version.py`; drop the `CHAT_STREAM_VERSION` cases in
`test_chat_stream_upstream.py`; update `test_config_onechat_base.py`. New:
`test_onechat_version.py` (resolver precedence + v1/v2/v3 `data`-unwrap),
per-request override e2e on HTTP + WS.

**Living docs:** `spec/openai-responses.md`, `spec/openai-responses-spec-gap-log.md`,
`context.md`. Dated historical plan docs under `docs/superpowers/plans/` are left
as-is (historical record).

## 9. Acceptance

- `resolve_version` returns the override when valid, else `v5`; invalid → `v5`.
- `resolve_model("onechat")` → `"onechat"`; anything else → 400.
- `events("v3")` unwraps the `data` envelope into one `answer` + one `done`;
  `events("v5")` streams SSE unchanged.
- HTTP POST and WS `response.create` with `onechat_version="v3"` both produce a
  valid `response.completed` sourced from `/v3/chat`.
- No reference to `CHAT_STREAM_VERSION` remains in `backend/app/` or
  `.env.prod.example`.
- Full backend suite green.
