# API Consumer Quickstart

This guide covers everything you need to start sending queries to the Thai Citizen Guide
gateway from your own application.

---

## Getting an API key

1. Sign in to the web application.
2. Open **Profile → API Keys → Create**.
3. Enter a name for the key and confirm.

The full key (prefixed `tcg_`) is displayed **once** at creation and is never shown again.
Copy it immediately. After creation only the first 12 characters (`key_prefix`) are visible
in the key list.

Confirmed against `backend/app/auth/security.py` (`API_KEY_PREFIX = "tcg_"`,
`generate_api_key` = prefix + 32 random URL-safe bytes) and
`backend/app/routers/api_key.py` (`CreatedAPIKeyResponse.key` returned only on `POST /api-keys/`;
`APIKeyResponse` exposes `key_prefix` only).

---

## Authentication

All protected endpoints use HTTP Bearer authentication. The Bearer token may be
**either** a `tcg_...` API key (recommended for programmatic/API consumers) **or**
a JWT access token from the `POST /api/v1/auth/login` flow (used by the web app):

```
Authorization: Bearer tcg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The REST routes and the MCP endpoints both resolve `tcg_` API keys the same way
(hash lookup in `UserAPIKey`); using an API key stamps its `last_used_at`. A key
inherits its owning user's role, so an admin's key works on admin-only endpoints.

Behavior on the optional-auth endpoints (chat, `/api/v1/conversations`):

- **No `Authorization` header** → anonymous (allowed; rate limits and quotas are
  not applied to anonymous traffic).
- **A valid API key or JWT** → authenticated as that user; rate limits and quotas
  apply.
- **A present-but-invalid `tcg_` key** → `401` (a deliberate auth attempt that
  fails is rejected, so a typo'd key can't silently bypass limits).
- **An expired/invalid JWT** → treated as anonymous (a browser's stale session
  token degrades gracefully rather than breaking anonymous-allowed endpoints).

Confirmed against `backend/app/auth/dependencies.py` (`_resolve_token` accepts both
token types) and `backend/app/mcp/server.py`.

---

## Base URL

The stack runs behind nginx (see `nginx/default.conf`). Nginx listens on port 8080 internally;
the externally published port is controlled by `EXTERNAL_HTTP_PORT` in the environment.

| Context | Base URL |
|---------|----------|
| Local dev (`docker compose up`) | `http://localhost:${EXTERNAL_HTTP_PORT}` — if the variable is unset the port is not bound; set it (e.g. `EXTERNAL_HTTP_PORT=8080`) or use the deployed gateway origin. |
| Deployed | Your deployment's origin (e.g. `https://chat.example.com`) |
All REST endpoints are under `/api/v1`. The examples below use
`BASE_URL=http://localhost:8080` as a placeholder.

---

## Endpoints

### `POST /api/v1/chat` — Synchronous response

Sends a query and waits for a complete answer.

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | `string` | yes | The citizen's question |
| `conversation_id` | `string` (UUID) | no | Continue an existing conversation; omit to start a new one |

Source: `backend/app/schemas/chat.py` — `ChatRequest`.

**Response body** (`200 OK`)

```json
{
  "success": true,
  "data": {
    "message_id": "<uuid>",
    "answer": "...",
    "references": [ { } ],
    "agentSteps": [ { } ],
    "agencies": [ { } ],
    "confidence": 0.0,
    "cached": false
  },
  "conversation_id": "<uuid>",
  "responseTime": 1234
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | `boolean` | Always `true` on 200 |
| `data.message_id` | `string` (UUID) | ID of the saved assistant message |
| `data.answer` | `string` | The AI-generated answer |
| `data.references` | `array` | Source references (array of objects; contents vary by upstream) |
| `data.agentSteps` | `array` | Intermediate agent steps (may be empty) |
| `data.agencies` | `array` | Agencies that contributed to the answer (may be empty) |
| `data.confidence` | `float` | Similarity confidence score (0.0 when not from cache) |
| `data.cached` | `boolean` | `true` when served from the similarity cache |
| `conversation_id` | `string` | The conversation UUID (new or existing) |
| `responseTime` | `integer` | Total response time in milliseconds |

Source: `backend/app/schemas/chat.py` — `ChatResponse` / `ChatResponseData`.

---

### `POST /api/v1/chat/stream` — Server-Sent Events (SSE) streaming

Sends a query and receives the answer as an SSE stream. The content type is
`text/event-stream`.

**Request body** — identical to `POST /api/v1/chat` (`ChatRequest`).

**Event stream format**

Each SSE event follows the standard format:

```
event: <event-name>
data: <JSON payload>

```

The server emits three named events:

| Event | Payload fields | Description |
|-------|---------------|-------------|
| `answer` | `answer`, `errors`, `sections`, … | The final answer data from the upstream (OneChat v4). Fields mirror the upstream response. |
| `error` | `message` (string), `code` (int) | Emitted when the upstream returns an error or times out. |
| `done` | `session_id`, `total_ms`, `message_id` | Final event. `message_id` is the saved assistant message UUID; present only when an answer was saved. |

The stream always ends with a `done` event. Clients should close the connection
after receiving it.

Source: `backend/app/routers/chat.py` — `chat_stream`, `_sse_event`, `event_generator`.

---

### `GET /api/v1/conversations` — List conversations

Returns the current user's conversation history. Requires authentication (a `tcg_`
API key or a JWT as the Bearer token).

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | `string` | `""` | Case-insensitive substring search in title |
| `filterAgency` | `string` | `""` | Filter by agency name |

**Response body** (`200 OK`)

```json
{
  "success": true,
  "data": [
    {
      "id": "<uuid>",
      "title": "How do I renew my passport?",
      "preview": "How do I renew my passport?",
      "date": "2026-06-12",
      "agencies": [],
      "status": "success",
      "message_count": 4,
      "response_time": "842"
    }
  ],
  "total": 1,
  "response_time": 12
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | `boolean` | Always `true` on 200 |
| `data` | `array` | List of `HistoryItem` objects |
| `data[].id` | `string` | Conversation UUID |
| `data[].title` | `string` | Conversation title (first 50 chars of first query) |
| `data[].preview` | `string` | Short preview (first 100 chars of first query) |
| `data[].date` | `string` | Date in `YYYY-MM-DD` format |
| `data[].agencies` | `array` | Agency names (currently always empty) |
| `data[].status` | `string` | Conversation status |
| `data[].message_count` | `integer` | Total message count |
| `data[].response_time` | `string` | Response time of the last turn |
| `total` | `integer` | Total number of conversations returned |
| `response_time` | `integer` | Query execution time in milliseconds |

Source: `backend/app/schemas/conversation.py` — `HistoryResponse`, `HistoryItem`;
`backend/app/routers/conversations.py` — `list_conversations`.

---

## Error envelope

All errors from this API (except 422 validation errors) use a consistent envelope:

```json
{
  "error": {
    "code": "<stable-code>",
    "message": "Human-readable description",
    "retryable": false
  }
}
```

The optional `upstream_status` field is included when an upstream agency returned an
error.

**Stable error codes**

| HTTP status | `code` | `retryable` |
|-------------|--------|-------------|
| 400 | `invalid_request` | `false` |
| 401 | `unauthorized` | `false` |
| 403 | `forbidden` | `false` |
| 404 | `not_found` | `false` |
| 429 | `rate_limited` | `true` |
| 500 | `internal` | `false` |
| 502 | `agency_unavailable` | `false` |
| 504 | `agency_timeout` | `false` |

`ApiError` instances raised in application code may use any string `code` with a
custom `retryable` flag.

**422 Validation errors** keep FastAPI's default shape (`{"detail": [...]}`) and are
not wrapped in the error envelope.

Source: `backend/app/errors.py` — `_STATUS_CODES` dict and `_envelope`.

---

## Interactive API docs

The FastAPI application exposes interactive OpenAPI docs at:

- **Swagger UI**: `{BASE_URL}/docs`
- **ReDoc**: `{BASE_URL}/redoc`
- **OpenAPI JSON**: `{BASE_URL}/openapi.json`

All three paths are proxied through nginx (see `nginx/default.conf` — the location regex
`^/(api|sse|messages|mcp|docs|redoc|openapi.json)` covers them).

Source: `backend/app/main.py` (`docs_url="/docs"`, `redoc_url="/redoc"`).

---

## Examples

### curl — synchronous chat

```bash
BASE_URL="http://localhost:8080"
TOKEN="tcg_your-api-key"   # an API key (tcg_...) or a JWT both work

curl -s -X POST "$BASE_URL/api/v1/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "ต้องใช้เอกสารอะไรบ้างในการต่ออายุหนังสือเดินทาง"
  }' | jq .
```

Example response:

```json
{
  "success": true,
  "data": {
    "message_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "answer": "การต่ออายุหนังสือเดินทางต้องใช้เอกสารดังนี้ ...",
    "references": [],
    "agentSteps": [],
    "agencies": [],
    "confidence": 0.0,
    "cached": false
  },
  "conversation_id": "1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed",
  "responseTime": 2341
}
```

---

### Python (httpx)

```python
import httpx

BASE_URL = "http://localhost:8080"
TOKEN = "tcg_your-api-key"   # an API key (tcg_...) or a JWT both work

with httpx.Client(base_url=BASE_URL) as client:
    resp = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"query": "วิธีแจ้งเกิดบุตรคืออะไร"},
    )
    resp.raise_for_status()
    data = resp.json()
    print(data["data"]["answer"])
```

To continue a conversation, pass the returned `conversation_id`:

```python
    follow_up = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={
            "query": "ต้องเสียค่าธรรมเนียมเท่าไหร่",
            "conversation_id": data["conversation_id"],
        },
    )
```

---

### JavaScript (fetch) — sync and SSE streaming

**Synchronous**

```javascript
const BASE_URL = "http://localhost:8080";
const token = "tcg_your-api-key"; // an API key (tcg_...) or a JWT both work

const resp = await fetch(`${BASE_URL}/api/v1/chat`, {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ query: "วิธีขอบัตรประชาชนใหม่" }),
});

const result = await resp.json();
console.log(result.data.answer);
```

**SSE streaming**

```javascript
async function streamChat(query, token) {
  const resp = await fetch(`${BASE_URL}/api/v1/chat/stream`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });

  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE events are delimited by double newlines
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop(); // keep incomplete trailing block

    for (const block of blocks) {
      const eventLine = block.split("\n").find(l => l.startsWith("event:"));
      const dataLine  = block.split("\n").find(l => l.startsWith("data:"));
      if (!dataLine) continue;

      const eventName = eventLine ? eventLine.slice(6).trim() : "message";
      const payload   = JSON.parse(dataLine.slice(5).trim());

      if (eventName === "answer") {
        console.log("Answer:", payload.answer);
      } else if (eventName === "error") {
        console.error("Error:", payload.message);
      } else if (eventName === "done") {
        console.log("Done. message_id:", payload.message_id);
        return payload;
      }
    }
  }
}

streamChat("ขั้นตอนการทำพาสปอร์ตสำหรับผู้เยาว์", token);
```

---

## OpenAI-compatible endpoint

Point the official OpenAI SDK at the portal — no portal-specific client needed.

```python
from openai import OpenAI

client = OpenAI(base_url="https://<host>/api/v1", api_key="tcg_...")

response = client.responses.create(
    model="thai-citizen-guide",
    input="ทำบัตรประชาชนหายต้องทำอย่างไร",
)
print(response.output_text)
```

Continue a conversation with `previous_response_id`:

```python
follow_up = client.responses.create(
    model="thai-citizen-guide",
    input="ต้องใช้เอกสารอะไรบ้าง",
    previous_response_id=response.id,
)
```

**Models:** `thai-citizen-guide` follows the configured upstream;
`thai-citizen-guide-v5` and `thai-citizen-guide-v4` pin it.

**Streaming:** `stream=True` emits the standard Responses event sequence. The answer
arrives as a single `response.output_text.delta` — the orchestrator produces a complete
answer rather than tokens — so streaming buys you connection semantics, not incremental text.

**WebSocket:** connect to `wss://<host>/api/v1/responses` with an `Authorization: Bearer`
header and send `{"type": "response.create", ...}` frames. One response is in flight at a
time; connections are closed after 60 minutes. `{"generate": false}` warms a conversation
without generating.

**Portal extras:** each response carries a non-standard top-level `portal` object with
`conversation_id`, the v5 `summary`, its `references`, `agency_ids`, and `cached`.

**Three things to know:** `store` is accepted but ignored — every turn is persisted for
analytics and audit. `usage` is always zero — the orchestrator does not report token counts.
Pipeline progress events are not surfaced; use `/api/v1/chat/stream` for those.

Full wire contract: [`spec/openai-responses.md`](../spec/openai-responses.md).

---

## See also

- [Agency Integration Guide](agency-integration.md) — connecting a government agency endpoint to the gateway
- [OpenAI Responses API wire contract](../spec/openai-responses.md) — the OpenAI-compatible endpoint's full spec
