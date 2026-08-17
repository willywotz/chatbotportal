# OpenAI Responses API endpoint — design

Date: 2026-07-22
Source spec: <https://developers.openai.com/api/docs/guides/websocket-mode> (WebSocket mode),
OpenAI Responses API reference (HTTP + SSE)
Branch: `feat/openai-responses-api` (off `feat/onechat-v5`)

## Goal

Expose the portal as an **OpenAI-compatible model provider**, so a third-party client can point
the official OpenAI SDK at us and get answers from the existing OneChat orchestration pipeline:

```python
client = OpenAI(base_url="https://host/api/v1", api_key="tcg_...")
client.responses.create(model="thai-citizen-guide", input="ขอถามเรื่องบัตรประชาชน")
```

Three transports, one pipeline:

| Transport | Endpoint | Notes |
|---|---|---|
| HTTP, non-streaming | `POST /api/v1/responses` | `stream: false` → one complete `Response` object |
| HTTP, streaming | `POST /api/v1/responses` | `stream: true` → OpenAI SSE event sequence |
| WebSocket | `wss://host/api/v1/responses` | same path, upgraded; `response.create` frames in, the same streaming events out |

This is an **additive** surface. `POST /chat`, `POST /chat/stream` and the SPA are untouched.

## Decisions

1. **Server side only.** We expose an OpenAI-compatible endpoint; we do not consume one. No
   OpenAI Responses upstream is added — OneChat stays the orchestrator.
2. **Backed by the OneChat v5 streaming path**, not the v3 sync path. Non-streaming is the same
   generator drained to completion, so all three transports share summary/references and one
   `save_turn()`.
3. **`model` selects the upstream.** `thai-citizen-guide-v5` / `-v4` pin the OneChat version
   per request; unknown model → 400.
4. **`previous_response_id` carries conversation continuity**, the idiomatic OpenAI mechanism.
5. **Portal extras ride in a top-level `portal` key**, not `metadata`.
6. **Anonymous access allowed**, matching `POST /chat`.
7. **`store` is accepted and ignored** — we always persist.
8. **The turn pipeline is extracted into a shared async generator** so the three transports are
   thin translators over one implementation.

## Architecture

### The shared seam: `app/services/chat/stream.py`

`routers/chat.py` is 473 lines and `chat_stream` inlines the whole turn: rate limit → quota →
similarity-cache lookup → session warm → upstream SSE → `save_turn` → `ConnectionLog` →
classification. `/responses` needs every one of those with a different wire format, so the pipeline
moves behind one interface:

```python
async def run_chat_turn(
    *, query: str, conversation_id: str, user: User | None,
    stream_version: str, background_tasks: BackgroundTasks | None = None,
) -> AsyncIterator[ChatEvent]: ...
```

`background_tasks` is optional because **WebSocket routes cannot use FastAPI `BackgroundTasks`** —
there is no response for the framework to hang them off. When it is `None` (the WS path), the
generator schedules `classify_message_category` with `asyncio.create_task` and keeps a reference
until it completes so it is not garbage-collected mid-flight. HTTP paths keep passing the real
`BackgroundTasks` so their behaviour is bit-for-bit what it is today.

`ChatEvent` is `(name: str, data: dict)` — the OneChat event vocabulary (`step`, `intent`,
`routing`, `agency_start`, `agency_responded`, `agency_verified`, `answer`, `done`, `error`),
unchanged. The generator owns cache replay, upstream connection, persistence and the terminal
`done` carrying `message_id`.

Consumers become translators:

| Consumer | Job |
|---|---|
| `routers/chat.py::chat_stream` | format each `ChatEvent` as `event:`/`data:` SSE — today's behaviour, no wire change |
| `routers/responses.py` (HTTP) | translate to OpenAI events; SSE or accumulate-and-return |
| `routers/responses.py` (WS) | same translation, `send_json` per frame |

The OpenAI translation itself lives in **`app/services/responses/translate.py`** — a pure,
synchronous function from `ChatEvent` to zero-or-more OpenAI event dicts, plus a builder for the
final `Response` object. Pure and transport-free, so it is where the tests concentrate.

`/chat/stream`'s existing tests are the safety net proving the extraction changed no behaviour.

### Routing and infrastructure

New router `app/routers/responses.py`, mounted `app.include_router(responses.router, prefix="/api/v1")`
in `main.py`. Prefix `/responses`, so the SDK's `base_url + "/responses"` lands correctly.
FastAPI keeps `@router.post("")` and `@router.websocket("")` on one path as distinct routes.

**nginx (`default.conf`) — two blocking changes.** The `/api` location today sets
`proxy_http_version 1.1` but passes no `Upgrade`/`Connection` headers, so the WS handshake would
400; and its `proxy_read_timeout 300s` would kill an idle socket at 5 minutes, well short of the
60-minute cap the protocol promises.

- Add `map $http_upgrade $connection_upgrade { default upgrade; '' close; }` at the **top of the
  file** — `conf.d/*.conf` is http context, so a `map` is legal there. A bare
  `proxy_set_header Connection "upgrade"` on `/api` would break keep-alive for every ordinary API
  request, hence the map.
- In the `/api` location: `proxy_set_header Upgrade $http_upgrade;` and
  `proxy_set_header Connection $connection_upgrade;`.
- Add `location = /api/v1/responses` with `proxy_read_timeout 3700s` (60-minute cap plus slack),
  otherwise identical to the `/api` block.

### Auth and limits

`get_current_user_optional`, exactly like `/chat`: a `tcg_` key or JWT if present, anonymous
otherwise, and a malformed `tcg_` key still 401s rather than degrading. Per authenticated turn:
`enforce_user_rate_limit` → `check_global_budget` → `check_user_quota`, unchanged.

Add `POST /api/v1/responses` to `_is_shared_write()` in `auth/dependencies.py` so `user`, `viewer`
and `auditor` keys pass the role chokepoint (mirroring the existing `/api/v1/chat` entries). The
WebSocket route bypasses the chokepoint entirely — it is a `websocket` route, not an HTTP one, and
global HTTP dependencies do not run on it. That is acceptable because the WS handler performs the
same optional-auth resolution itself and no role is denied chat access anyway, but it must be
stated so nobody assumes the chokepoint covers it.

**Known gap, accepted:** anonymous callers skip rate limiting and quota, on both transports. This
matches `/chat` today. On a 60-minute WebSocket it means an anonymous socket can issue unlimited
turns. Mitigated only by the connection cap below; a per-IP limiter is out of scope here and
recorded in "Future work".

## Request mapping

| OpenAI field | Handling |
|---|---|
| `model` | `thai-citizen-guide` → follow `CHAT_STREAM_VERSION`; `thai-citizen-guide-v5` / `thai-citizen-guide-v4` → pin that upstream. Unknown → 400 `invalid_request_error`, `param: "model"` |
| `input` | `str` → the query. `list` → the last item with `role: "user"`, concatenating its `input_text` content parts. Final item not a user message, or empty after trimming → 400 |
| `previous_response_id` | `resp_<assistant_message_uuid>` → load that `Message` → its `conversation_id`. Unknown → 404 `previous_response_not_found` |
| `conversation` | a raw portal `conversation_id`. Supplied together with `previous_response_id` and disagreeing → 400 |
| `stream` | bool, default `false` (HTTP only; WS always streams) |
| `store` | accepted, **ignored** — the portal always records turns for analytics, audit and the similarity cache. Documented loudly in `docs/quickstart.md`; a client expecting zero data retention would otherwise be misled |
| `instructions`, `temperature`, `max_output_tokens`, `tools`, `metadata`, `top_p`, … | accepted and ignored, never an error — the SDK sends many fields we cannot honour and rejecting them would break ordinary clients |

Continuity reuses the existing path: resolve `conversation_id`, `Conversation.get` (404 if
missing), then `ensure_session_warmed()`. A `previous_response_id` chain therefore behaves
identically to a `conversation_id` chain from the SPA.

Requests with no continuation field start a new conversation and are eligible for the similarity
cache, exactly as a new `/chat/stream` turn is.

## Response shape

```json
{
  "id": "resp_<assistant_message_id>",
  "object": "response",
  "created_at": 1753142400,
  "status": "completed",
  "model": "thai-citizen-guide-v5",
  "output": [
    {
      "id": "msg_<assistant_message_id>",
      "type": "message",
      "role": "assistant",
      "status": "completed",
      "content": [{"type": "output_text", "text": "<answer>", "annotations": []}]
    }
  ],
  "output_text": "<answer>",
  "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
  "portal": {
    "conversation_id": "0198...",
    "summary": "…",
    "references": [{"number": 1, "agency_id": "…", "agency_name": "…", "url": null}],
    "agency_ids": ["…"],
    "cached": false,
    "stream_version": "v5"
  }
}
```

- `output_text` is the composed `answer` — byte-identical to what the SPA renders, summary prefix
  included. We do **not** strip it; `stripSummaryPrefix` is a presentation concern of our own UI.
- `portal` rather than `metadata`: OpenAI types `metadata` as a flat `dict[str, str]` (16 keys,
  512 chars each) and the SDK validates it, so `references[]` in there can break real clients. SDK
  response models ignore unknown top-level keys.
- `usage` is zeroed. OneChat does not report token counts to the portal, and inventing them would
  corrupt any client-side cost accounting. Documented as always-zero.

### Error envelope

This router alone uses OpenAI's shape rather than `app/errors.py`:

```json
{"error": {"message": "...", "type": "invalid_request_error", "param": "model", "code": null}}
```

`type` is `invalid_request_error` for 4xx and `server_error` for 5xx. A dedicated exception handler
scoped to the `/responses` routes keeps the rest of the API on the existing envelope.

## Streaming (HTTP SSE)

OneChat v5 delivers the answer as a single terminal `answer` event, not token deltas. The stream is
therefore a correct OpenAI event sequence containing **one large delta**:

1. `response.created` — `status: "in_progress"`, id already allocated
2. `response.output_item.added`
3. `response.content_part.added`
4. `response.output_text.delta` — the whole answer
5. `response.output_text.done`
6. `response.content_part.done`
7. `response.output_item.done`
8. `response.completed` — the full `Response` object above, `portal` included

Every event carries a monotonically increasing `sequence_number` starting at 0, and the standard
`item_id` / `output_index` / `content_index` fields.

**Upstream progress events (`step`, `agency_start`, `agency_responded`, …) are dropped.** Injecting
non-standard SSE event types is exactly what breaks strict SDK parsers, and there is no standard
Responses event that carries them. Clients wanting the pipeline view use `/chat/stream`.

If OneChat ever emits incremental text, the translator emits multiple `output_text.delta` events
with no change to this design — that is the reason for the single-delta shape rather than skipping
deltas altogether.

Failures emit `response.failed` with the error object, then close.

## WebSocket mode

`wss://host/api/v1/responses`, `Authorization: Bearer` header (optional, per the anonymous
decision). Browsers cannot set headers on a WebSocket; browser clients are not a target here and
should use the SSE transport. No query-parameter token fallback — it would leak keys into access
logs.

| Concern | Behaviour |
|---|---|
| Inbound | `response.create` only. Any other `type`, or malformed JSON → an `error` frame; the socket stays open |
| Payload | The same fields as the HTTP body, plus `type` and `generate` |
| Sequencing | One in-flight response per socket. A `response.create` arriving mid-flight is queued and run after the current one. No multiplexing — parallel work needs parallel connections |
| `generate: false` | Warmup: resolve the conversation and run `ensure_session_warmed()`, emit no `response.*` events. Direct fit with `services/session.py` |
| Continuity | A connection-local dict maps the most recent `resp_<id>` → `conversation_id`; a miss falls back to the DB lookup, then `previous_response_not_found` |
| Connection cap | Server closes at 60 minutes with `websocket_connection_limit_reached`, matching the documented error text |
| Outbound | The identical event objects from the SSE sequence, one JSON object per text frame |
| `store` | Accepted, ignored — same as HTTP |

The connection-local cache being per-connection means `uvicorn --workers 4` needs no shared state:
OpenAI's own semantics are connection-local, and the DB fallback covers cross-connection
continuation.

**`RESPONSES_WS_MAX_CONNECTIONS`** (new setting, default 100, `SETTINGS_GROUPS` group `"Chat"`):
an unauthenticated endpoint holding hour-long sockets is otherwise an unbounded resource sink. Over
the cap, the handshake is rejected with close code 1013 (try again later).

## Config additions (`app/config.py`)

| Setting | Default | Purpose |
|---|---|---|
| `RESPONSES_WS_MAX_CONNECTIONS` | `100` | Concurrent WebSocket cap |
| `RESPONSES_WS_MAX_DURATION_SECONDS` | `3600` | The 60-minute connection cap, configurable for tests |

Both in the `"Chat"` group so they are editable at `/settings`.

## Testing (TDD — failing test first, every step)

`backend/tests/test_responses_api.py`, upstream mocked the way the existing v5 stream tests mock it.

**Extraction safety net:** the existing `/chat/stream` suite must pass unchanged after
`run_chat_turn()` is extracted, before any `/responses` code is written.

**Translator (`services/responses/translate.py`) — pure, no transport:**
- `answer` event → the full 8-event sequence in order
- `sequence_number` is 0-based and strictly increasing
- `portal` block carries summary, references, agency_ids, cached, stream_version
- degrade case (no `summary`) produces a valid response with empty summary/references
- upstream `step` / `agency_*` events produce zero OpenAI events

**HTTP:**
- non-streaming happy path returns a complete `Response` with `output_text`
- streaming returns the exact event order above
- `previous_response_id` round-trip: create → feed the returned id back → same `conversation_id`
- `conversation` param resolves; conflicting pair → 400
- unknown `model` → 400 with the OpenAI error envelope; each valid model pins the right upstream
- unknown `previous_response_id` → 404 `previous_response_not_found`
- `input` as string, as array, array whose last item is not a user message (400), empty query (400)
- unsupported fields (`tools`, `temperature`, `store`) are ignored, not errors
- anonymous call succeeds; `user`-role `tcg_` key passes the chokepoint
- similarity-cache hit path returns `portal.cached: true`
- one `save_turn` + one `ConnectionLog` per turn, no double-persist across transports
- classification is scheduled exactly once per turn on both the `BackgroundTasks` and the
  `asyncio.create_task` path

**WebSocket** (`TestClient.websocket_connect`):
- handshake, then `response.create` → the full event sequence as frames
- two sequential `response.create` on one socket both complete
- a create arriving mid-flight is queued, not interleaved
- `generate: false` warms the session and emits no `response.*` events
- `previous_response_id` served from the connection cache, and from the DB on a fresh socket
- unknown id → `previous_response_not_found` frame, socket stays open
- malformed frame → `error` frame, socket stays open
- duration cap (with `RESPONSES_WS_MAX_DURATION_SECONDS` lowered) closes with
  `websocket_connection_limit_reached`
- connection cap rejects the handshake over `RESPONSES_WS_MAX_CONNECTIONS`

## Documentation

- `docs/quickstart.md` — a new section: SDK snippet, the three model ids, continuity via
  `previous_response_id`, the `portal` block, and explicit notes that `store` is ignored, `usage`
  is zero, and progress events are not surfaced.
- `spec/openai-responses.md` — the wire contract we implement, mirroring `spec/v5.md`'s role.
- `CONTEXT.md` — new endpoint, new router, the `services/chat/stream.py` seam, the nginx WebSocket
  change, and the two new settings.

## Rollout

- Branch `feat/openai-responses-api` off `feat/onechat-v5`; PR into `dev` once v5 has landed there.
- Purely additive: no migration, and rollback is removing the router mount.
- On merge to `main`: update `CONTEXT.md` and rebuild docker compose.

## Out of scope

- Consuming an OpenAI Responses upstream (`services/chat/dispatch.py` and OneChat are unchanged).
- Audio / Realtime API modalities — OneChat has no audio pipeline.
- `tools` / function calling. Agency dispatch is the orchestrator's job, not the client's.
- Real token accounting in `usage` — blocked on OneChat reporting counts.
- Per-IP rate limiting for anonymous callers.
- `/responses/compact` and `context_management` from the upstream guide.
- Any frontend change; the SPA keeps using `/chat/stream`.
