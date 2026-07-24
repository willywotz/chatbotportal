# OpenAI Responses API — wire contract

The portal exposes an **OpenAI-compatible model provider** so that the official OpenAI SDK
(or any client that speaks the Responses API) can talk to the OneChat orchestration pipeline
without a portal-specific client. This document is the wire contract the implementation must
match; every shape below is copied from the code, not invented — see the "Source" line under
each section.

Three transports, one pipeline (`app/routers/responses.py`):

| Transport | Endpoint | `stream` |
|---|---|---|
| HTTP, non-streaming | `POST /api/v1/responses` | `false` (default) — one complete `Response` object |
| HTTP, SSE | `POST /api/v1/responses` | `true` — the OpenAI event sequence |
| WebSocket | `wss://<host>/api/v1/responses` | always streams — `response.create` frames in, the same events out |

All three drive the same generator (`run_response()` in `app/routers/responses.py`), so their
event output cannot drift from one another.

### Endpoint scope

The upstream OpenAI Responses reference (`spec/openai-responses-api/1-responses.md`) declares
seven endpoints. The portal now implements response **creation, retrieval, deletion, and
input-item listing**, and registers the three OneChat-incompatible endpoints as explicit
`501 Not Implemented` stubs. The full wire contract for everything beyond creation lives in
**`spec/openai-responses-extended.md`** — read it for the retrieve/delete/input_items shapes, the
Conversations + items family, ephemeral temp-user auth, and soft-delete semantics.

| Upstream endpoint | Status | Note |
|---|---|---|
| `POST /responses` | ✅ Implemented | HTTP, SSE, and WebSocket transports (above) |
| `GET /responses/{id}` | ✅ Implemented | Reconstructed from the stored assistant `Message` — extended spec § 1 (`cached`/`stream_version`/`model` are best-effort, not persisted per-turn) |
| `DELETE /responses/{id}` | ✅ Implemented | **Soft** delete (`deleted_at`); the turn is retained for analytics/audit but 404s afterward — extended spec § 2 |
| `POST /responses/{id}/cancel` | ⚠️ 501 stub | Registered, returns `501` `not_implemented`: a turn is one synchronous OneChat call, no `background` mode to cancel — extended spec § 4 |
| `POST /responses/compact` | ⚠️ 501 stub | Registered, returns `501` `not_implemented`: OneChat owns context/history server-side — extended spec § 4 |
| `GET /responses/{id}/input_items` | ✅ Implemented | Lists the single preceding user message (only the newest is ever forwarded, § 2.1) — extended spec § 3 |
| `POST /responses/input_tokens` | ⚠️ 501 stub | Registered, returns `501` `not_implemented`: OneChat does not report token counts (see `usage` deviation below) — extended spec § 4 |

Retrieve/delete/input_items and the Conversations family enforce **ephemeral temp-user ownership**
(extended spec § 0.2). Clients needing the three `501` operations must not treat the portal as a
drop-in for the full OpenAI Responses API.

#### Conversations API — implemented (see `spec/openai-responses-extended.md` §§ 5–6)

The upstream reference also defines a **Conversations** family (`spec/openai-responses-api/2-conversations.md`)
and its **items** subresource (`spec/openai-responses-api/3-conversations-items.md`). The portal
now implements **all** of these as OpenAI-compatible endpoints, backed by the existing
`Conversation`/`Message` store (`app/routers/openai_conversations.py`).

Conversations resource (`2-conversations.md`):

| Upstream endpoint | Status |
|---|---|
| `POST /conversations` | ✅ Implemented (extended § 5.1) |
| `GET /conversations/{id}` | ✅ Implemented (extended § 5.2) |
| `POST /conversations/{id}` (update) | ✅ Implemented — replaces `metadata` (extended § 5.3) |
| `DELETE /conversations/{id}` | ✅ Implemented — soft delete (extended § 5.4) |

Items subresource (`3-conversations-items.md`) — all four endpoints it declares:

| Upstream endpoint | Status |
|---|---|
| `POST /conversations/{id}/items` (create items) | ✅ Implemented — persisted as `Message` rows, no effect on generation (extended § 6.2) |
| `GET /conversations/{id}/items` (list items) | ✅ Implemented — keyset pagination (extended § 6.3) |
| `GET /conversations/{id}/items/{item_id}` (retrieve an item) | ✅ Implemented (extended § 6.4) |
| `DELETE /conversations/{id}/items/{item_id}` (delete an item) | ✅ Implemented — soft delete (extended § 6.5) |

Ids are `conv_<uuid>`/`msg_<uuid>`; items map `Message` rows to the `conversation.item` message
shape. Injected items are stored for retrieval but do **not** change what OneChat generates (only
the newest user message is ever forwarded, § 2.1).

⚠️ **The native SPA history router moved to `/api/v1/conversations` → `/api/v1/history`**
(`app/routers/conversations.py`) to free `/api/v1/conversations` for the OpenAI-compatible surface
above. The native contract (save-with-messages, list-with-search, get, delete) is unchanged except
for the prefix and is **not** OpenAI-shaped.

---

## 1. Models

`model` selects the OneChat upstream. Unknown model → `400 invalid_request_error`, `param: "model"`.

| `model` | Upstream |
|---|---|
| `thai-citizen-guide` | Follows `CHAT_STREAM_VERSION` (default `v5`) |
| `thai-citizen-guide-v5` | Pinned to OneChat v5 |
| `thai-citizen-guide-v4` | Pinned to OneChat v4 |

Source: `MODEL_IDS` and `resolve_model()` in `app/services/responses/request.py`.

```json
{ "error": { "message": "Unknown model 'gpt-5'. Supported models: thai-citizen-guide, thai-citizen-guide-v4, thai-citizen-guide-v5.", "type": "invalid_request_error", "param": "model", "code": null } }
```

---

## 2. Request body

```json
{
  "model": "thai-citizen-guide",
  "input": "",
  "previous_response_id": null,
  "conversation": null,
  "stream": false,
  "store": true,
  "generate": true
}
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `model` | `string` | `"thai-citizen-guide"` | See § 1 |
| `input` | `string \| array` | `""` | See § 2.1 |
| `previous_response_id` | `string \| null` | `null` | See § 3 |
| `conversation` | `string \| null` | `null` | See § 3 |
| `stream` | `boolean` | `false` | HTTP only — the WebSocket transport always streams |
| `store` | `boolean` | `true` | Accepted, ignored — see § 6 |
| `generate` | `boolean` | `true` | WebSocket only — `false` warms a conversation without generating; see § 8 |

Any other field the OpenAI SDK sends (`temperature`, `tools`, `max_output_tokens`,
`instructions`, `metadata`, `top_p`, …) is accepted and silently ignored — the schema is
`extra="ignore"`, so unsupported fields never produce an error.

Source: `ResponsesRequest` in `app/schemas/responses.py`;
`test_unsupported_fields_are_accepted_and_ignored`,
`test_store_and_generate_default_true` in `backend/tests/services/test_responses_request.py`.

### 2.1 `input` forms

`input` reduces to a single query string. OneChat keeps conversation history server-side, so
only the newest user message is forwarded — earlier items in a client-supplied array are
context the upstream already has.

**String** — used as-is (trimmed):

```json
{ "input": "บัตรประชาชนหาย" }
```

**Array** — the *last* item must have `role: "user"`; its `content` is either a plain string
or a list of content parts, each part's `text` joined with a space:

```json
{
  "input": [
    { "role": "user", "content": [{ "type": "input_text", "text": "first" }] },
    { "role": "assistant", "content": [{ "type": "output_text", "text": "answer" }] },
    { "role": "user", "content": [{ "type": "input_text", "text": "second" }] }
  ]
}
```

→ query is `"second"`. Multiple text parts on the last item join with a space
(`"part one" + "part two"` → `"part one part two"`). A plain string `content` on the last item
is accepted directly (`{"role": "user", "content": "hello"}` → `"hello"`).

**Rejected as `400 invalid_request_error`, `param: "input"`** with one of these exact `message`
values:

| Cause | `message` |
|---|---|
| Empty string, whitespace-only string, empty array, or last item's `content` is `null` / a non-string-non-list / trims to empty | ``` `input` must not be empty. ``` |
| Last array item is not a `role: "user"` message | ``` The last item of `input` must be a message with role 'user'. ``` |

Source: `extract_query()` in `app/services/responses/request.py`;
`backend/tests/services/test_responses_request.py`.

---

## 3. Conversation continuity

A response id has the shape `resp_<assistant message uuid>`. Continuing a conversation loads
that message and reads its `conversation_id` — the same mechanism `/chat/stream` uses under the
hood, so a `previous_response_id` chain behaves identically to a `conversation_id` chain from
the SPA.

| Field | Behavior |
|---|---|
| `previous_response_id` | `resp_<uuid>` → look up that assistant `Message` → its `conversation_id`. Not found or malformed → `404`, `code: "previous_response_not_found"`, `param: "previous_response_id"` |
| `conversation` | A raw portal `conversation_id`. May be supplied alone, or together with `previous_response_id` if it resolves to the *same* conversation (compared as UUID values, so textual case never causes a spurious conflict). Supplied together and disagreeing → `400 invalid_request_error`, `param: "conversation"`, `message` ``` `conversation` does not match the conversation of `previous_response_id`; supply only one. ``` |
| Neither supplied | A new conversation id is generated; the turn is eligible for the similarity cache like any new `/chat/stream` turn |

On the WebSocket transport, a connection-local `dict[str, str]` (response id → conversation id)
is checked before the database lookup, mirroring OpenAI's connection-local semantics; a cache
miss falls back to the same DB lookup as HTTP.

```json
{ "error": { "message": "Previous response with id 'resp_...' not found", "type": "invalid_request_error", "param": "previous_response_id", "code": "previous_response_not_found" } }
```

`conversation_not_found` (`404`, `param: "conversation"`) is a distinct case: the id resolves
(from `previous_response_id`, `conversation`, or the WS cache) but no `Conversation` row exists
for it — e.g. it was deleted, or a WS `generate: false` warm-up targets a stale id.

Source: `app/services/responses/continuity.py`; the `conversation_not_found` raise sites in
`app/routers/responses.py` (`run_response`, via `ConversationNotFound`) and
`app/services/responses/session.py` (`WsSession._warm`).

---

## Upstream input — the OneChat `ChatEvent` stream

Everything in §§ 4–7 is a *translation* of the upstream turn, so a rebuild needs this **input**
contract as much as the output shapes below. `run_turn()` yields `ChatEvent(name, data)` values
(the OneChat pipeline vocabulary, unchanged) and `ResponseAccumulator.consume()` maps each one to
zero or more OpenAI events:

| `ChatEvent.name` | Drives | Notes |
|---|---|---|
| `answer` | The six output-item events (§ 5, events 2–7) and the populated response body (§ 4) | The terminal answer, delivered whole — OneChat does not stream token deltas |
| `done` | `response.completed` (§ 5, event 8) | Ends the turn; suppressed if a `response.failed` was already emitted |
| `error` | `response.failed` (§ 7) | Mid-stream upstream failure; `data["message"]` is copied verbatim into `response.error.message` |
| `step`, `intent`, `routing`, `agency_start`, `agency_responded`, `agency_verified` | *Nothing* | Pipeline-progress events, dropped (§ 5.1) |

The `answer` event's `data` is the **sole** source of the answer text, summary, references and
agency ids that §§ 4 and 6 expose:

```json
{
  "answer": "คำตอบเต็ม",
  "summary": "สรุป",
  "references": [{ "number": 1, "agency_id": "a-1", "agency_name": "กรมการปกครอง", "url": null }],
  "sections": [{ "agencies": [{ "id": "a-1", "name": "กรมการปกครอง" }] }]
}
```

| `data` key | Becomes | Notes |
|---|---|---|
| `answer` | `output_text` and every `output_text` field (§ 4, § 5) | Leading/trailing whitespace trimmed; missing or empty → `""` |
| `summary` | `portal.summary` (§ 6) | v5 only; `""` on v4 or a degraded summary |
| `references` | `portal.references` (§ 6) | Passed through verbatim — OneChat v5 shape |
| `sections[].agencies[].id` | `portal.agency_ids` (§ 6) | The `id` of each agency, flattened across every section |

Source: `ChatEvent` and `run_turn()` in `app/services/chat/stream.py`;
`ResponseAccumulator.consume` / `_answer_events` in `app/services/responses/translate.py`.

---

## 4. Response object

Non-streaming (`stream: false`) returns one complete object; streaming and the WebSocket
transport deliver the same object as the `response` field of the terminal
`response.completed` (or `response.failed`) event.

```json
{
  "id": "resp_11111111-1111-1111-1111-111111111111",
  "object": "response",
  "created_at": 1753142400,
  "status": "completed",
  "model": "thai-citizen-guide-v5",
  "output": [
    {
      "id": "msg_11111111-1111-1111-1111-111111111111",
      "type": "message",
      "status": "completed",
      "role": "assistant",
      "content": [{ "type": "output_text", "text": "คำตอบเต็ม", "annotations": [] }]
    }
  ],
  "output_text": "คำตอบเต็ม",
  "usage": { "input_tokens": 0, "output_tokens": 0, "total_tokens": 0 },
  "portal": {
    "conversation_id": "c-1",
    "summary": "สรุป",
    "references": [{ "number": 1, "agency_id": "a-1", "agency_name": "กรมการปกครอง", "url": null }],
    "agency_ids": ["a-1"],
    "cached": false,
    "stream_version": "v5"
  }
}
```

| Field | Notes |
|---|---|
| `id` | `resp_<assistant message uuid>` |
| `model` | Echoes the requested `model` **verbatim** — the default id stays `"thai-citizen-guide"`, not the resolved `"…-v5"` (§ 1) |
| `status` | `"in_progress"` (on `response.created`), `"completed"`, or `"failed"` |
| `output` / `output_text` | `output` is empty and `output_text` is `""` until the answer arrives — and `output` stays `[]` even in a `completed` response whose answer is empty (the degrade case); `output_text` is the composed `answer`, including any v5 summary prefix — no summary-side stripping, though leading/trailing whitespace is trimmed |
| `usage` | Always the zero object — see § 6 |
| `portal` | Non-standard top-level block — see § 6 |
| `error` | Present only on a failed response — see § 7 |

Source: `ResponseAccumulator._response_body` in `app/services/responses/translate.py`;
`test_completed_carries_the_final_response`, `test_portal_block_carries_the_v5_extras`,
`test_degrade_case_without_summary_still_completes` in
`backend/tests/services/test_responses_translate.py`.

---

## 5. Streaming — the 8-event sequence

OneChat delivers the answer as one terminal event, not token deltas, so a stream is a valid
OpenAI event sequence containing a **single large delta**. Every event carries a
zero-based, strictly increasing `sequence_number`.

```
response.created
response.output_item.added
response.content_part.added
response.output_text.delta      ← the whole answer, in one delta
response.output_text.done
response.content_part.done
response.output_item.done
response.completed              ← carries the full Response object (§ 4)
```

```json
{ "type": "response.created", "sequence_number": 0, "response": { "...": "status: in_progress, output: [], output_text: \"\"" } }
```

```json
{ "type": "response.output_item.added", "sequence_number": 1, "output_index": 0, "item": { "id": "msg_...", "type": "message", "status": "in_progress", "role": "assistant", "content": [] } }
```

```json
{ "type": "response.content_part.added", "sequence_number": 2, "item_id": "msg_...", "output_index": 0, "content_index": 0, "part": { "type": "output_text", "text": "", "annotations": [] } }
```

```json
{ "type": "response.output_text.delta", "sequence_number": 3, "item_id": "msg_...", "output_index": 0, "content_index": 0, "delta": "คำตอบเต็ม" }
```

```json
{ "type": "response.output_text.done", "sequence_number": 4, "item_id": "msg_...", "output_index": 0, "content_index": 0, "text": "คำตอบเต็ม" }
```

```json
{ "type": "response.content_part.done", "sequence_number": 5, "item_id": "msg_...", "output_index": 0, "content_index": 0, "part": { "type": "output_text", "text": "คำตอบเต็ม", "annotations": [] } }
```

```json
{ "type": "response.output_item.done", "sequence_number": 6, "output_index": 0, "item": { "id": "msg_...", "type": "message", "status": "completed", "role": "assistant", "content": [{ "type": "output_text", "text": "คำตอบเต็ม", "annotations": [] }] } }
```

```json
{ "type": "response.completed", "sequence_number": 7, "response": { "...": "the full Response object, § 4" } }
```

Over HTTP SSE, each event is framed as `event: <type>\ndata: <json>\n\n`, and the stream
terminates with the literal line `data: [DONE]`. On the WebSocket, each event is one JSON text
frame (no `event:`/`data:` framing, no `[DONE]` sentinel — the sequence simply ends).

All JSON on this surface — SSE `data:` payloads, WebSocket frames, and non-streaming/error bodies
alike — is serialized as UTF-8 with `ensure_ascii=False`, so Thai and other non-ASCII text appears
literally (e.g. `คำตอบเต็ม`) and is **never** `\uXXXX`-escaped.

**Upstream pipeline-progress events are dropped.** `step`, `intent`, `routing`, `agency_start`,
`agency_responded` and `agency_verified` produce zero OpenAI events — there is no standard
Responses event that carries them, and injecting non-standard SSE event types is exactly what
breaks strict SDK parsers. Clients wanting the pipeline view use `/api/v1/chat/stream`.

### 5.1 Event scope — 9 of 53 upstream events

The upstream OpenAI streaming reference (`spec/openai-responses-api/4-streaming-events.md`)
declares **53 event types**. The portal emits the **9** listed in the sequence above (the 8-event
happy path plus `response.failed` on a mid-stream failure) and deliberately emits none of the
other 44. This is a scope decision, not an oversight: the omitted events all announce features
OneChat does not surface through this endpoint (tool calls, reasoning, audio, image generation,
MCP, code interpreter, refusals, and the background/queued lifecycle). A client must not wait for
any of them — a portal stream is the 9-event set and nothing else.

| Upstream event(s) | Status | Note |
|---|---|---|
| `response.created`, `response.output_item.added`, `response.content_part.added`, `response.output_text.delta`, `response.output_text.done`, `response.content_part.done`, `response.output_item.done`, `response.completed` | ✅ Emitted | The 8-event happy path (§ 5) |
| `response.failed` | ✅ Emitted | Mid-stream upstream failure (§ 7) |
| `response.in_progress`, `response.queued`, `response.incomplete` | ❌ Out of scope | The portal only transitions `created → completed` (or `created → failed`); no background/queued mode (§ 8) and no truncated/incomplete status |
| `error` | ❌ Out of scope | The SSE-level error event is never emitted — pre-stream failures return the HTTP error envelope (§ 7) and mid-stream failures use `response.failed`. WS `error` frames are a separate, non-OpenAI shape (§ 8) |
| `response.refusal.delta`, `response.refusal.done` | ❌ Out of scope | No refusal channel; answers are plain `output_text` |
| `response.output_text.annotation.added` | ❌ Out of scope | `annotations` is always `[]` (§ 4); none are streamed |
| `response.function_call_arguments.delta` / `.done`, `response.custom_tool_call_input.delta` / `.done` | ❌ Out of scope | No function or custom tool calling |
| `response.file_search_call.*`, `response.web_search_call.*` | ❌ Out of scope | No hosted file-search or web-search tools |
| `response.mcp_call_arguments.*`, `response.mcp_call.*`, `response.mcp_list_tools.*` | ❌ Out of scope | No MCP tool surface |
| `response.code_interpreter_call.*`, `response.code_interpreter_call_code.*` | ❌ Out of scope | No code interpreter |
| `response.image_generation_call.*` | ❌ Out of scope | No image generation |
| `response.reasoning_summary_part.*`, `response.reasoning_summary_text.*`, `response.reasoning_text.*` | ❌ Out of scope | No reasoning surface exposed |
| `response.audio.*`, `response.audio.transcript.*` | ❌ Out of scope | Text-only; no audio modality |

Source: the `"type": "response.*"` literals in `ResponseAccumulator` in
`app/services/responses/translate.py` are the only nine event types the module emits.

**Two error timings, not one:**

- **Before the stream starts** — request-validation failures (unknown `model`, unknown
  `previous_response_id`, empty `input`) are detected in the prelude of
  `run_response()`, before any bytes are sent. They are returned as a normal HTTP error response
  with the JSON error envelope (§ 7), **not** as an SSE event, even when `stream: true` was
  requested — HTTP status and headers are already committed by the time an SSE body iterator
  could run.
- **Mid-stream** — a failure from the upstream OneChat call arrives as a `response.failed` event
  (see § 7) inside an already-committed `200` stream: `response.created`, then
  `response.failed`, then `data: [DONE]`. No `response.completed` follows.

Source: `ResponseAccumulator.created_event` / `consume` / `_answer_events` in
`app/services/responses/translate.py`; `create_response` (SSE framing, the `data: [DONE]`
terminator) in `app/routers/responses.py`;
`test_full_event_sequence_and_order`, `test_sequence_numbers_are_zero_based_and_strictly_increasing`
in `backend/tests/services/test_responses_translate.py`;
`test_streaming_emits_the_openai_sequence`, `test_streaming_unknown_model_returns_400_over_http`,
`test_streaming_unknown_previous_response_id_returns_404_over_http`,
`test_upstream_error_becomes_response_failed` in `backend/tests/routers/test_responses_http.py`.

---

## 6. `portal` block

```json
{
  "conversation_id": "0198...",
  "summary": "สรุปครับ ...",
  "references": [{ "number": 1, "agency_id": "a-1", "agency_name": "กรมการปกครอง", "url": null }],
  "agency_ids": ["a-1"],
  "cached": false,
  "stream_version": "v5"
}
```

| Field | Notes |
|---|---|
| `conversation_id` | The portal's conversation id |
| `summary` | The v5 executive summary (empty string on v4, or if summary generation degraded) |
| `references[]` | Same shape OneChat v5 emits — see `spec/api/v5.md § 4.3` |
| `agency_ids` | Agency ids that contributed, gathered from every section's agencies |
| `cached` | `true` when the turn was served from the similarity cache |
| `stream_version` | `"v5"` or `"v4"` — the upstream that actually served this turn |

Source: `ResponseAccumulator._response_body`, `_answer_events` in
`app/services/responses/translate.py`.

---

## 7. Error envelope

```json
{ "error": { "message": "...", "type": "invalid_request_error", "param": null, "code": null } }
```

`type` is `"invalid_request_error"` for client errors and `"server_error"` for unexpected 5xx
failures. This router uses this shape instead
of the portal's `app/errors.py` envelope, via a dedicated exception handler scoped to
`/api/v1/responses`.

Source: `ResponsesApiError.envelope()` in `app/services/responses/errors.py`.

**Codes confirmed in the code:**

| `code` | HTTP status | `type` | Where |
|---|---|---|---|
| `previous_response_not_found` | 404 | `invalid_request_error` | `app/services/responses/continuity.py` |
| `conversation_not_found` | 404 | `invalid_request_error` | `app/services/responses/session.py`, `app/routers/responses.py` |
| `websocket_connection_limit_reached` | — (WS close, not an HTTP status) | `invalid_request_error` | `app/routers/responses.py` (`_connection_limit_frame`) |
| `no_answer` | 502 | `server_error` | `app/routers/responses.py` (`create_response`) — the non-streaming path ran to completion without a `response.completed` or `response.failed` |

Some errors carry no `code` at all (`code: null`) — e.g. unknown `model`, empty `input`, or a
`conversation`/`previous_response_id` mismatch — the `param` field identifies the offending
field instead.

**Mid-stream failures** use `code: "server_error"` inside the `response.failed` event's
`response.error` object (not the top-level envelope), carrying the upstream's message verbatim:

```json
{ "type": "response.failed", "sequence_number": 1, "response": { "status": "failed", "error": { "code": "server_error", "message": "OneChat v5 returned 502" }, "...": "rest of the Response object" } }
```

Source: `ResponseAccumulator._failed` in `app/services/responses/translate.py`.

---

## 8. WebSocket mode

`wss://<host>/api/v1/responses`. `Authorization: Bearer <token>` is optional (anonymous is
allowed, matching `POST /chat`); there is no query-parameter token fallback, since that would
leak keys into access logs. Browsers cannot set headers on a WebSocket, so browser clients
should use the SSE transport instead.

### 8.1 Event scope — 1 client event, 9 of 53 server events

The upstream OpenAI WebSocket reference (`spec/openai-responses-api/5-websocket-events.md`)
declares **1 client event** (`response.create`) and **53 server events**. That server set is
identical to the streaming reference's 53 events (`4-streaming-events.md`), so the § 5.1 split
applies here unchanged.

| Direction | Upstream declares | Portal | Status |
|---|---|---|---|
| Client → server | `response.create` (1) | Accepts only `response.create`; any other `type` → an `error` frame | ✅ 1 of 1 |
| Server → client | 53 events | The same **9** as § 5.1 (the 8-event happy path plus `response.failed`), one JSON object per text frame | ✅ 9 of 53; the other 44 out of scope, same reasons as § 5.1 |

One nuance beyond § 5.1: the upstream **`error` server event** is out of scope. The portal does
send `{"type": "error", ...}` frames (below), but that is the portal's own envelope shape, **not**
the OpenAI `error` event — a strict client must not parse it as the upstream `error` type. As over
SSE, a client must not wait for any of the other 44 server events; a portal socket carries the
9-event set and the portal `error` frame, nothing else.

Source: `WsSession.handle_text` in `app/services/responses/session.py` (accepts `response.create`
only; wraps errors via `_error_frame`); `ResponseAccumulator` in
`app/services/responses/translate.py` (the same nine `response.*` literals emitted over every
transport).

**Inbound frames** — JSON text frames. Only `{"type": "response.create", ...}` is accepted; the
rest of the body is the same `ResponsesRequest` fields as the HTTP body (§ 2):

```json
{ "type": "response.create", "model": "thai-citizen-guide", "input": "บัตรหาย" }
```

**Outbound frames** — the identical event objects from § 5, one JSON object per text frame, no
`event:`/`data:` framing.

**Sequencing:** one response in flight per socket. The router awaits `handle_text()` fully
before reading the next frame, so a `response.create` arriving mid-generation simply queues in
the socket's receive buffer rather than interleaving with the in-flight response.

**`generate: false` — warm-up frame.** Resolves the conversation (via `previous_response_id`
and/or `conversation`, same rules as § 3) and calls `ensure_session_warmed()` without invoking
the pipeline. No `response.*` event is emitted at all — not even on success. If the resolved
conversation does not exist, a `conversation_not_found` error frame is sent instead:

```json
{ "type": "response.create", "previous_response_id": "resp_...", "generate": false }
```

**Errors keep the connection open.** A frame that fails validation, or an unexpected server
fault while generating, produces an `error` frame — the socket is never closed for it:

| Situation | Frame |
|---|---|
| Invalid JSON | `{"type": "error", "error": {"message": "Frame is not valid JSON.", "type": "invalid_request_error", "param": null, "code": null}}` |
| Binary (non-text) frame | `{"type": "error", "error": {"message": "This endpoint accepts text frames only; binary frames are not supported.", "type": "invalid_request_error", "param": null, "code": null}}` |
| Wrong/missing `type` | `{"type": "error", "error": {"message": "Unsupported frame type; this endpoint accepts \`response.create\` only.", "type": "invalid_request_error", "param": "type", "code": null}}` |
| Body fails `ResponsesRequest` validation | `{"type": "error", "error": {"message": "<pydantic ValidationError text>", "type": "invalid_request_error", "param": null, "code": null}}` |
| A `ResponsesApiError` raised while generating (e.g. `previous_response_not_found`) | Its own `envelope()`, wrapped in `{"type": "error", ...}` |
| Any other unhandled exception while generating | `{"type": "error", "error": {"message": "An unexpected error occurred.", "type": "server_error", "param": null, "code": null}}` |

The last row is the `invalid_request_error` vs `server_error` distinction: client-caused
problems (bad frame, known `ResponsesApiError`) are `invalid_request_error`; an unanticipated
exception inside `_generate` is logged server-side and reported as `server_error` without
leaking its message.

**Connection limit.** The server closes the socket after
`RESPONSES_WS_MAX_DURATION_SECONDS` (default `900`, 15 minutes), sending this frame first
and then closing with code `1000`. The message interpolates the configured duration in seconds:

```json
{ "type": "error", "error": { "message": "Responses websocket connection limit reached (900 seconds). Create a new websocket connection to continue.", "type": "invalid_request_error", "param": null, "code": "websocket_connection_limit_reached" } }
```

A new handshake beyond `RESPONSES_WS_MAX_CONNECTIONS` (default `1024`) concurrent sockets is
refused at `accept()` time with WebSocket close code `1013` ("try again later") — no frame is
sent, since the connection was never accepted.

Source: `WsSession.handle_text` in `app/services/responses/session.py`;
`_connection_limit_frame`, `_ConnectionRegistry`, `responses_websocket` in
`app/routers/responses.py`; `test_malformed_frame_does_not_kill_the_connection`,
`test_connection_cap_refuses_the_next_connection` in
`backend/tests/routers/test_responses_ws_route.py`.

---

## Deviations from the OpenAI contract

| Deviation | Reason |
|---|---|
| `store` is accepted but ignored — every turn is persisted | The portal records turns for analytics, audit and the similarity cache. A client expecting zero retention must not use this endpoint. |
| `usage` is always zero | OneChat does not report token counts to the portal; inventing them would corrupt client-side cost accounting. |
| Pipeline progress (`step`, `agency_*`) is not surfaced | No standard Responses event carries it, and non-standard SSE event types break strict SDK parsers. Use `/chat/stream` for the pipeline view. |
| A non-standard top-level `portal` object carries summary/references/agency ids | OpenAI types `metadata` as a flat string map that the SDK validates; structured data there breaks real clients. SDK models ignore unknown top-level keys. |
