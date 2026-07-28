# Unified Chat Endpoint — Design

**Date:** 2026-07-27
**Status:** Approved (brainstorming), pending implementation plan
**Scope:** `backend/app/routers/chat.py` + supporting service/schema/frontend changes

## 1. Goal

Merge the three chat routes into **one path** (`/chat`) exposed over three
transports — HTTP JSON, SSE, and WebSocket — all driven by the single existing
turn pipeline, and let a caller select any OneChat upstream version (v1–v5) via
an OpenAI-style `model` field.

### Today

| Route | Transport | Upstream | Notes |
|---|---|---|---|
| `POST /chat` | JSON | OneChat **v3** (`chat_v3`) | Delegates to `/chat/external` |
| `POST /chat/external` | JSON | OneChat v3 | Deprecated internal alias |
| `POST /chat/stream` | SSE | v5 pipeline (`run_turn`) | Frontend streaming path |

The sync path (`chat_external`) and the stream path (`run_turn`) are **two
different pipelines**. This design collapses both onto the one transport-free
core that already exists.

## 2. Key facts that shape the design

- **One URL, protocol-dispatched.** Starlette routes match on both path *and*
  ASGI `scope["type"]`, so `@router.post("")` (`http`) and
  `@router.websocket("")` (`websocket`) coexist on the same `/chat` path. HTTP
  POST and SSE share one function (SSE is just a `text/event-stream` response);
  WebSocket must be its own function.
- **The core already exists.** `app/services/chat/stream.py` (`prepare_turn` +
  `run_turn`) is transport-free: it handles the similarity cache, upstream call,
  persistence (`save_turn`), `ConnectionLog`, and category classification —
  including a WebSocket-safe background-task fallback (`_schedule_classification`).
- **The client already supports all versions.** `OneChatClient.events()`
  (`app/services/onechat/client.py`) is a *uniform* event stream: v4/v5 stream
  SSE natively; v1/v2/v3 (JSON upstream) are adapted into a single `answer` +
  `done` event. `resolve_version()` picks the version; `prepare_turn` already
  accepts `requested_version`.
- **`responses.py` is the working template** for exactly this shape: one `POST`
  (`stream` body field → JSON or SSE) + one `@router.websocket`, all over
  `run_turn`, with a connection cap, header-bearer WS auth, and a deadline.

Consequence: "support all versions" is **not** new pipeline work. It is threading
a version selector through to `prepare_turn`. The transports sit on top of the
one version-agnostic core.

## 3. Endpoint surface (target)

```
POST /chat     stream=false -> JSON  (version-faithful envelope)
               stream=true  -> SSE   (text/event-stream)
WS   /chat     {query, conversation_id?, model?} frames -> {event, data} frames
```

`/chat/external` and `/chat/stream` are **deleted** (hard cutover; frontend
migrated in the same change).

## 4. Request schema

`ChatRequest` (`app/schemas/chat.py`) gains two optional fields:

```python
class ChatRequest(BaseModel):
    query: str
    conversation_id: str | None = None
    stream: bool = False
    model: str | None = None
```

- `stream` selects JSON vs SSE on the POST handler. (Ignored by WS, which is
  always streaming.)
- `model` selects the OneChat version, OpenAI Responses-style.

### Model → version mapping

A small resolver (new, e.g. `app/services/chat/model.py` or a helper in the
onechat service):

| `model` value | Version |
|---|---|
| omitted / `null` / `"onechat"` | `v5` (newest) |
| `"onechat-v1"` … `"onechat-v5"` | `v1` … `v5` |
| anything else (typo/unknown) | `v5` (lenient) |

Lenient fallback matches the existing `resolve_version()` behavior. Implemented
by stripping an `onechat-` prefix and delegating to `resolve_version()`, so the
version vocabulary stays single-sourced.

## 5. The core (unchanged)

Both HTTP and WS call the existing pipeline:

```
prepare_turn(query, conversation_id, user, is_continuation, requested_version)
    -> TurnPlan            # may raise ConversationNotFound (-> 404)
run_turn(plan, background_tasks)
    -> async iterator of ChatEvent(name, data)   # answer / step / agency_* / done / error
```

No changes to `stream.py` are required for versions — `run_turn` already drives
any version via `get_client(version).events()`.

## 6. Transport adapters

### 6.1 `POST /chat`

```
1. query = body.query.strip(); 400 if empty
2. conversation_id = body.conversation_id or new uuid
3. version = resolve_model_version(body.model)
4. plan = await prepare_turn(..., requested_version=version)   # 404 on ConversationNotFound
5a. stream=true  -> StreamingResponse over run_turn, framed by _sse_event (as today)
5b. stream=false -> await collect_turn(plan) -> JSONResponse (envelope below)
```

The 400/404 checks run **before** any streaming body starts (same ordering the
current `chat_stream` and `responses.create_response` use), so errors are real
HTTP status codes, not mid-stream events.

### 6.2 Sync aggregation — `collect_turn`

New transport-free helper (in `stream.py` or a sibling module) that drains
`run_turn` and folds events into a result:

- capture the `answer` event's `data` (version-shaped),
- collect pipeline events (`step`, `agency_*`) — reused via
  `build_pipeline_snapshot` for `agentSteps`, mirroring `_persist`,
- read `message_id` / `total_ms` from the terminal `done` event,
- surface an `error` event as an error envelope.

Persistence still happens inside `run_turn` (draining it triggers `_persist`),
so the sync path gets identical persistence for free.

### 6.3 Sync JSON envelope (version-faithful passthrough)

```json
{
  "success": true,
  "data": {
    "message_id": "…",
    "cached": false,
    "agentSteps": [ … ],
    "…": "…the version's answer-event payload, passed through…"
  },
  "conversation_id": "…",
  "responseTime": 66351
}
```

`data` carries the version's own answer shape unchanged:

| Version | answer-event `data` fields surfaced |
|---|---|
| v1 | `answer`, `agencies[]`, `errors[]` |
| v2 | `agencies[]`, `errors[]` (no `answer`) |
| v3 / v4 | `answer`, `sections[]`, `errors[]`, `debug` |
| v5 | v4 fields + `summary`, `references[]` |

Plus `message_id`, `cached`, and `agentSteps` (from the pipeline snapshot) on
every version. On an upstream error the envelope is
`{ "success": false, "error": "…", "conversation_id": "…" }` (mirrors the
existing error envelope shape).

### 6.4 `WS /chat`

Mirrors `responses.py`'s WebSocket:

- `_ConnectionRegistry` cap via new setting `CHAT_WS_MAX_CONNECTIONS`.
- Header-bearer auth only (`_ws_user`); browsers that cannot set WS headers use
  SSE. No query-param token (would leak into logs).
- Per-connection deadline via new setting `CHAT_WS_MAX_DURATION_SECONDS`.
- Loop: each **text** frame is a JSON `{query, conversation_id?, model?}`; run one
  turn to completion (one in flight at a time), emitting each `ChatEvent` as a
  JSON text frame `{ "event": name, "data": {…} }`. Binary frames and malformed
  input get an error frame. `WebSocketDisconnect` ends the loop.

The connection-cap + header-auth helpers are near-identical to `responses.py`'s.
Extract a shared helper (`app/services/chat/ws.py`) **only if** it stays clean;
otherwise a small local copy is acceptable (frame vocabulary differs).

## 7. Deletions / cleanup (`chat.py`)

- Remove `chat_external` (v3 sync path) and its `chat_v3` usage from the router.
- Remove `chat_stream` and the delegating `chat` wrapper.
- Remove dead helpers `_copy_cached_answer` and `_parse_sse_block` (unused after
  cutover; `_parse_sse_block`'s only test targets the onechat client's copy, not
  this one).
- Keep `_sse_event`.
- Keep the `_stream_version` re-export (`tests/routers/test_chat_stream_version.py`).
- `chat_v3` on `OneChatClient` stays (still used by `events()` for v3); only the
  router stops calling it directly.

## 8. Frontend changes

- `chatApi.ts`: collapse `sendChatQuery` + `sendChatQuerySSE` onto the single
  `/api/v1/chat` endpoint, selecting SSE via `stream: true` in the body (instead
  of the current separate `/chat/stream` path). Optional `model` passthrough.
- `ChatApiResponse`: updated to the version-faithful envelope.
- `agencyApi.ts`: read agency data from the passthrough `data` (was v3-only
  `agencies`/`confidence`).
- `useChat.ts`: consumes `agentSteps` / `answer` — minor shape adjustment only.

## 9. Testing (TDD — mandatory)

New tests (write failing first):

- `POST /chat` JSON, default version (v5): envelope shape, message_id, cached.
- `POST /chat` `stream: true`: SSE events end-to-end.
- `WS /chat`: connect → send query frame → receive event frames → `done`;
  connection-cap rejection; header auth; malformed/binary frame → error frame.
- Model → version: `onechat-v1..v5` select the right upstream; `onechat` and
  unknown → v5; JSON passthrough differs correctly per version (v2 has no
  `answer`; v3 has `sections`/`debug`; v5 has `summary`/`references`).
- `400` empty query; `404` unknown conversation (before stream starts).
- Similarity-cache replay path returns `cached: true`.

Rewrite or delete tests bound to removed routes: `test_chat_external_client`,
`test_chat_stream_*`, `test_chat_cache`, `test_surface_parity`, and the
`_copy_cached_answer` test in `tests/services/test_chat_turn.py`.

## 10. Out of scope

- No change to the OneChat client, `run_turn`, `save_turn`, or persistence
  semantics.
- No change to the OpenAI Responses router (`responses.py`).
- No new OneChat versions or upstream behavior.

## 11. Risks

- **Hard cutover** breaks any non-frontend client of `/chat/stream` or
  `/chat/external`. Accepted per decision.
- **Sync response shape change** (v3 fixed shape → version-faithful passthrough)
  requires the coordinated frontend update; both ship in the same change.
- **WS auth** is header-only by design; browser WS clients must use SSE.
