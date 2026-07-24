# OpenAI Responses API — extended surface (retrieve, delete, input_items, conversations, items)

This is the wire contract for the endpoints the base spec (`spec/openai-responses.md`)
marks **Out of scope**. It supersedes those rows once implemented. Read the base spec first —
this document assumes its vocabulary (`resp_<uuid>`, the `portal` block, the §7 error envelope,
UTF-8 `ensure_ascii=False`).

Two classes of previously-out-of-scope work:

- **Kind 1 — implemented for real**, backed by the existing `Conversation`/`Message` store:
  response retrieve/delete/input_items, and the full Conversations + items family.
- **Kind 2 — registered but `501 Not Implemented`**, because OneChat exposes no backing
  capability: `POST /responses/{id}/cancel`, `POST /responses/input_tokens`,
  `POST /responses/compact`. The 44 streaming/WS event types stay absent (no source data) —
  no code, unchanged from the base spec.

---

## 0. Cross-cutting decisions

### 0.1 Namespace move — native SPA router relocates

The native SPA history router (`app/routers/conversations.py`) moves off `/api/v1/conversations`
to **`/api/v1/history`**, freeing `/api/v1/conversations` for the OpenAI-compatible surface. The
native contract is unchanged except for the prefix:

| Was | Now |
|---|---|
| `POST /api/v1/conversations` | `POST /api/v1/history` |
| `GET /api/v1/conversations` | `GET /api/v1/history` |
| `GET /api/v1/conversations/{id}` | `GET /api/v1/history/{id}` |
| `GET /api/v1/conversations/{id}/messages` | `GET /api/v1/history/{id}/messages` |
| `DELETE /api/v1/conversations/{id}` | `DELETE /api/v1/history/{id}` |

Frontend callers updated: `frontend/src/features/history/historyApi.ts`,
`frontend/src/features/dashboard/useRealtimeActivity.ts`,
`frontend/src/features/history/useConversationMessages.ts`,
`frontend/src/mocks/handlers.ts`, `frontend/src/features/history/HistoryPage.test.tsx`.
Auth chokepoint updated: `app/auth/dependencies.py` — `_CONVERSATION_PATH`,
`_CONVERSATION_MESSAGES_GET_PATTERN`, `_is_shared_write` retargeted to `/api/v1/history`, and a
new allowlist entry added for the OpenAI `/api/v1/conversations` surface.

### 0.2 Authorization — ephemeral temp-user ownership

Every endpoint in this document enforces `owner == caller`. Ownership is by `user_id` on the
`Conversation`/`Message` row.

- **Authenticated caller** (JWT or `tcg_` API key): owner is that `User`.
- **Anonymous caller**: on a *create* (`POST /responses`, `POST /conversations`), the server
  mints an **ephemeral `User`** (`is_ephemeral=True`, unusable password hash, role `user`) and a
  JWT (`create_access_token({"sub": <temp user id>})`), sets it as the row owner, and returns the
  token in a response header:

  ```
  X-Portal-Session: <jwt>
  ```

  The client re-sends it as `Authorization: Bearer <jwt>` on later calls. Without it, the caller
  cannot retrieve/delete/list rows it created anonymously (each fresh anonymous call is a new temp
  user). The token's TTL is `JWT_EXPIRE_MINUTES`; ephemeral users are flagged for later pruning
  (pruning itself is out of scope for this work).
- **Ownership failure**: a resolved id whose owner ≠ caller returns the same shape as "not found"
  — `404`, so ownership is never disclosed. Never `403` (that would confirm the row exists).

`POST /responses` (existing) gains temp-user minting + the `X-Portal-Session` header for anonymous
callers; its event output is otherwise unchanged.

### 0.3 Soft delete

`DELETE` never destroys data — the base spec guarantees turns are retained for analytics/audit.
Each delete sets `deleted_at = now()` and returns OpenAI's `{... "deleted": true}`. Every
**addressable** read path (one that serves a row by its id) filters `deleted_at IS NULL`:

- `Conversation.deleted_at` (new, nullable) — a deleted conversation 404s on retrieve, is omitted
  from native history lists, and its items 404.
- `Message.deleted_at` (new, nullable) — a deleted item/turn 404s and is omitted from lists,
  from `input_items`, and from `previous_response_id`/`conversation` continuity resolution.

**Known exception — the similarity cache.** The content-similarity answer cache
(`app/services/similarity.py`), which reuses a recent assistant answer for a *semantically similar
new question* within `SIMILARITY_WINDOW_SECONDS` (default 60s), does **not** filter `deleted_at`.
A soft-deleted turn's answer may therefore resurface as a cached reply to a similar question inside
that short window. This is consistent with the base-spec framing that turns are retained for
analytics/audit (soft delete is not privacy erasure), and the cache reuses answer *content* (public
agency information) by semantic match, never re-serving the deleted `resp_<id>` itself. Filtering the
cache by `deleted_at` is a tracked follow-up, not part of this surface.

### 0.4 ID prefixes

| Wire prefix | Portal id |
|---|---|
| `resp_<uuid>` | assistant `Message.id` |
| `conv_<uuid>` | `Conversation.id` |
| `msg_<uuid>` | `Message.id` |

Prefixes are **accepted-and-stripped** on input and always emitted on output. A malformed or
non-UUID id after stripping is a not-found (`404`), not a `500`. Continuity (`conversation` field
on `POST /responses`) also accepts a `conv_`-prefixed id.

### 0.5 New Pydantic schemas

`app/schemas/openai_conversations.py` (new):
`ConversationCreateRequest`, `ConversationUpdateRequest`, `ItemsCreateRequest`, plus the
message-item content model. All use `ConfigDict(extra="ignore")` (matches `ResponsesRequest`).

---

## 1. Response retrieve — `GET /api/v1/responses/{response_id}`

Reconstructs the §4 Response object from the stored assistant `Message`. `response_id` is
`resp_<uuid>` (prefix optional).

- **200** — the full §4 Response object with `status: "completed"`, rebuilt from the Message:
  `output`/`output_text` from `content`, `portal.summary` from `summary`,
  `portal.references` from `summary_references`, `portal.agency_ids` from `agency_ids`,
  `portal.conversation_id` from `conversation_id`.
- **Reconstruction caveats** (fields not persisted per-turn): `portal.cached` is always `false`;
  `portal.stream_version` is `"v5"` when a `summary` exists, else `"v4"`; `created_at` is
  `int(message.created_at.timestamp())`. `usage` is the zero object (unchanged).
- **404** `previous_response_not_found`-style — not an assistant message, malformed id, soft-deleted,
  or owner ≠ caller:

  ```json
  { "error": { "message": "Response with id 'resp_...' not found", "type": "invalid_request_error", "param": "response_id", "code": "response_not_found" } }
  ```

Query params (`include`, `stream`, `starting_after`) are accepted and ignored.

## 2. Response delete — `DELETE /api/v1/responses/{response_id}`

Soft-deletes the assistant `Message` (the turn). Owner-checked.

- **200**:

  ```json
  { "id": "resp_11111111-...", "object": "response", "deleted": true }
  ```

- **404** `response_not_found` — same conditions as §1 (already deleted → 404).

## 3. Response input items — `GET /api/v1/responses/{response_id}/input_items`

Lists the input that produced the response. Per base-spec §2.1, only the newest user message is
ever forwarded, so this returns the **single user `Message` immediately preceding** the assistant
message in the same conversation (soft-deleted rows excluded). Owner-checked.

- **200** — OpenAI list envelope:

  ```json
  {
    "object": "list",
    "data": [
      { "id": "msg_<uuid>", "type": "message", "role": "user", "status": "completed",
        "content": [{ "type": "input_text", "text": "บัตรประชาชนหาย" }] }
    ],
    "first_id": "msg_<uuid>",
    "last_id": "msg_<uuid>",
    "has_more": false
  }
  ```

  Empty list (`data: []`, `first_id`/`last_id` `null`, `has_more` false) when no preceding user
  message exists.
- Query params `limit` (1–100, default 20), `order` (`asc`|`desc`, default `desc`), `after`,
  `include` are accepted; `include` ignored. With a single item, `limit`/`order`/`after` are
  effectively no-ops but validated.
- **404** `response_not_found` — same as §1.

## 4. Kind 2 stubs — `501 Not Implemented`

`POST /responses/{id}/cancel`, `POST /responses/input_tokens`, `POST /responses/compact` are
registered (so they appear in the OpenAI schema and 404 is never returned for a wrong reason) and
return the §7 envelope with HTTP `501`:

```json
{ "error": { "message": "`cancel` is not supported: a turn is one synchronous OneChat call with no background mode to cancel.", "type": "invalid_request_error", "param": null, "code": "not_implemented" } }
```

| Endpoint | `message` |
|---|---|
| `POST /responses/{id}/cancel` | `` `cancel` is not supported: a turn is one synchronous OneChat call with no background mode to cancel. `` |
| `POST /responses/input_tokens` | `` `input_tokens` is not supported: OneChat does not report token counts to the portal. `` |
| `POST /responses/compact` | `` `compact` is not supported: OneChat owns context/history server-side. `` |

`type` is `invalid_request_error`, `code` is `not_implemented`, `status` is `501`. (Add `status`
support for 501 to `ResponsesApiError`; it already carries an arbitrary `status`.)

---

## 5. Conversations

The `Conversation` row gains a `metadata` JSON field (OpenAI metadata: ≤16 entries, keys ≤64
chars, values ≤512 chars — validated on write). `conv_<uuid>` on the wire.

### 5.1 Create — `POST /api/v1/conversations`

Body (`extra="ignore"`):

```json
{ "metadata": { "topic": "demo" }, "items": [ { "type": "message", "role": "user", "content": "hi" } ] }
```

- Creates a `Conversation` (owner = caller or freshly-minted temp user; `X-Portal-Session` header
  on anonymous). Optional `items` (≤20) are persisted as `Message` rows (see §6 mapping).
- **200** — the conversation object:

  ```json
  { "id": "conv_<uuid>", "object": "conversation", "created_at": 1753142400, "metadata": { "topic": "demo" } }
  ```
- `metadata` validation failure → `400 invalid_request_error`, `param: "metadata"`.
- `items` length > 20 → `400`, `param: "items"`.

### 5.2 Retrieve — `GET /api/v1/conversations/{conversation_id}`

- **200** — conversation object (as above). Owner-checked.
- **404** `conversation_not_found` — missing, soft-deleted, or owner ≠ caller.

### 5.3 Update — `POST /api/v1/conversations/{conversation_id}`

Only `metadata` is updatable. `metadata` **replaces** (not merges) the stored value.

- **200** — updated conversation object.
- **404** `conversation_not_found`; `400 param: "metadata"` on invalid metadata.

### 5.4 Delete — `DELETE /api/v1/conversations/{conversation_id}`

Soft-deletes the conversation and cascades a soft-delete to its messages.

- **200**:

  ```json
  { "id": "conv_<uuid>", "object": "conversation.deleted", "deleted": true }
  ```
- **404** `conversation_not_found`.

---

## 6. Conversation items

An item is a `Message` mapped to OpenAI's `conversation.item` (message) shape. `msg_<uuid>`.

### 6.1 Item ⇄ Message mapping

| OpenAI item field | Message source |
|---|---|
| `id` | `msg_<Message.id>` |
| `type` | `"message"` |
| `role` | `Message.role` (`user`\|`assistant`\|`system`\|`developer` — stored verbatim; the CharField(20) already fits) |
| `status` | `"completed"` |
| `content[]` | one part: `input_text` for `role in {user, system, developer}`, `output_text` for `assistant`; `text` = `Message.content` |

**Content flattening on write:** a create-item `content` that is a string is used as-is; a list of
parts joins each part's `text` with a space (mirrors base-spec §2.1). Missing/empty text → `""`.

### 6.2 Create items — `POST /api/v1/conversations/{conversation_id}/items`

Body: `{ "items": [ {message item}, ... ] }` (≤20). Query `include` accepted+ignored. Owner-checked.
Persists each as a `Message` (owner = caller). Does **not** affect generation (base-spec §2.1).

- **200** — the OpenAI list envelope of the **created** items (in request order):

  ```json
  { "object": "list", "data": [ { "id": "msg_<uuid>", "type": "message", "role": "user", "status": "completed", "content": [{ "type": "input_text", "text": "hi" }] } ], "first_id": "msg_<uuid>", "last_id": "msg_<uuid>", "has_more": false }
  ```
- **404** `conversation_not_found`; **400** `param: "items"` on >20 or an item missing `role`.

### 6.3 List items — `GET /api/v1/conversations/{conversation_id}/items`

Lists the conversation's `Message` rows (soft-deleted excluded). Owner-checked.

- Query `limit` (1–100, default 20), `order` (`asc`|`desc`, default `desc` — by `created_at`),
  `after` (a `msg_<uuid>` cursor, exclusive), `include` (ignored).
- **200** — list envelope; `has_more` true when more rows exist beyond `limit`; `first_id`/`last_id`
  are the page bounds (`null` on an empty page).
- **404** `conversation_not_found`.

### 6.4 Retrieve item — `GET /api/v1/conversations/{conversation_id}/items/{item_id}`

- **200** — the single item object. Owner-checked; item must belong to the conversation and not be
  soft-deleted.
- **404** — `conversation_not_found` (bad conversation) or `item_not_found`
  (`param: "item_id"`, `code: "item_not_found"`) for a bad/foreign/deleted item.

### 6.5 Delete item — `DELETE /api/v1/conversations/{conversation_id}/items/{item_id}`

Soft-deletes the `Message`. Owner-checked.

- **200**:

  ```json
  { "id": "msg_<uuid>", "object": "conversation.item.deleted", "deleted": true }
  ```
- **404** — `conversation_not_found` or `item_not_found`.

---

## 7. Error envelope & new codes

All errors reuse `ResponsesApiError.envelope()` (base-spec §7). The dedicated exception handler's
scope extends to `/api/v1/conversations`. New codes:

| `code` | HTTP | `type` | Where |
|---|---|---|---|
| `response_not_found` | 404 | `invalid_request_error` | responses retrieve/delete/input_items |
| `conversation_not_found` | 404 | `invalid_request_error` | conversations + items (reuses the existing code) |
| `item_not_found` | 404 | `invalid_request_error` | item retrieve/delete |
| `not_implemented` | 501 | `invalid_request_error` | Kind 2 stubs (§4) |

Metadata/items validation failures carry `code: null` and identify the field via `param`.

---

## 8. What stays out of scope (unchanged from base spec)

The 44 streaming/WS event types (tool calls, reasoning, audio, image, MCP, code interpreter,
refusals, annotations, background/queued lifecycle) remain unemitted — OneChat surfaces no source
data for them. This document adds **no** new streaming events; the portal stream is still the
9-event set (base-spec §5.1).
