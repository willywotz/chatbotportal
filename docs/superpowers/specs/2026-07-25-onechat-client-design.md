# OneChat Client — Unified Backend Access to `spec/api/`

**Date:** 2026-07-25
**Branch:** `feat/onechat-client`
**Status:** Approved for planning

## 1. Purpose

Give `backend/` first-class access to every chat endpoint documented in
`spec/api/` — `/v1/chat`, `/v2/chat`, `/v3/chat`, `/v4/chat` (SSE),
`/v5/chat` (SSE), and `/health`.

Today backend only wires v3/v4/v5, via three hardcoded full URLs, with the
HTTP/SSE calls duplicated inline across four call sites. This spec introduces a
single OneChat client that owns transport for all six endpoints and migrates the
existing call sites onto it.

**Out of scope:** `/v1/mcp/agencies` and `/v1/mcp/health` (deferred). No changes
to the standalone onechat service itself — this is backend-side only.

## 2. Module & Interface

New package: `backend/app/services/onechat/`, with `client.py`.

The client owns **transport only**: payload assembly, HTTP/SSE, response parsing,
and error mapping. All business logic — persistence, similarity-cache probe,
session warm-up, tracing spans, ConnectionLog writes — stays in the current
callers.

```python
SseEvent = tuple[str, dict]           # (event_name, data)

class OneChatError(Exception):
    """Any non-2xx or transport failure from onechat, with the upstream status."""
    status_code: int                  # HTTP status, or 504 timeout / 502 transport
    message: str

class OneChatClient:
    async def chat_v1(query, mcp_endpoint_url, session_id=None) -> dict   # synthesized answer
    async def chat_v2(query, mcp_endpoint_url, session_id=None) -> dict   # raw per-agency
    async def chat_v3(query, mcp_endpoint_url, session_id=None) -> dict   # structured + debug

    def   stream_v4(query, mcp_endpoint_url, session_id=None) -> AsyncIterator[SseEvent]
    def   stream_v5(query, mcp_endpoint_url, session_id=None) -> AsyncIterator[SseEvent]
    def   stream_by_version(version, query, mcp_endpoint_url, session_id=None) -> AsyncIterator[SseEvent]

    async def health() -> dict           # {"status": "ok"}
```

Details:

- **Payload** is uniform across chat endpoints:
  `{"query", "mcp_endpoint_url", "session_id"}`. `session_id` is omitted when
  `None` (onechat generates one). `query`/`mcp_endpoint_url` default to
  `settings.MCP_ENDPOINT_URL` at the call site, not inside the client.
- **`_parse_sse_block`** moves out of `services/chat/stream.py` into the client;
  streaming methods yield raw `(name, data)` events and do not interpret them.
- **`stream_by_version`** backs the `CHAT_STREAM_VERSION` selection currently in
  `_stream_upstream()`. Unknown version → fall back to `v5` with a warning
  (preserving today's behavior).
- **Timeouts** come from settings (`EXTERNAL_CHAT_TIMEOUT` for sync,
  `V4_STREAM_TIMEOUT` for stream), passed by the client, not hardcoded.
- **Error mapping:** non-200 sync → `OneChatError(status_code, body[:200])`;
  `httpx.ReadTimeout` → `OneChatError(504, ...)`; other transport →
  `OneChatError(502, ...)`. On the stream path the client raises the same error;
  the caller decides how to translate it into `error`/`done` events (today's
  `_stream_live` behavior is preserved by the caller, not the client).

## 3. Config change

Replace the three hardcoded full URLs with one base URL and derive paths.

```python
# before
ONECHAT_V3_URL = "http://185.84.160.55:8000/v3/chat"
ONECHAT_V4_URL = "http://185.84.160.55:8000/v4/chat"
ONECHAT_V5_URL = "http://185.84.160.55:8000/v5/chat"

# after
ONECHAT_BASE_URL = "http://185.84.160.55:8000"
# client derives: {base}/v1/chat … {base}/v5/chat, {base}/health
```

Touch points for this rename:

- `app/config.py` — swap the three keys for `ONECHAT_BASE_URL`.
- `SETTINGS_GROUPS["OneChat"]` — replace `ONECHAT_V3_URL/V4_URL/V5_URL` with
  `ONECHAT_BASE_URL` (keep `CHAT_STREAM_VERSION`, `MCP_ENDPOINT_URL`). This group
  feeds the admin `/settings` UI and is DB-overridable; a missing key here has
  broken a test before, so the group list and its tests must be updated in lockstep.
- `.env` and `.env.example` — replace the three vars with `ONECHAT_BASE_URL`.
- Any stored DB overrides for the old keys become inert; documented as a manual
  re-set in the admin UI (no migration — settings are re-enterable).

## 4. Call-site migration

| Call site | Today | After |
|---|---|---|
| `services/session.py` `ensure_session_warmed` | inline POST to `onechat_url` | `client.chat_v3(query, mcp, session_id)` |
| `services/chat/stream.py` `_stream_live` | inline `client.stream` + local SSE parse | `client.stream_by_version(version, ...)` |
| `services/chat/stream.py` `_stream_upstream` | returns `(version, url)` | resolves version only; url derived in client |
| `routers/chat.py` (v3 sync `/chat`, `/chat/external`) | inline POST to `ONECHAT_V3_URL` | `client.chat_v3(...)` |
| `routers/responses.py` + `services/responses/request.py` | picks `ONECHAT_V4/V5_URL` | resolves version → `client.stream_v4/v5` |

`ensure_session_warmed` keeps its `onechat_url` parameter removed in favor of the
client (it currently takes `onechat_url` + `mcp_endpoint_url`; after migration it
takes the client/version + `mcp_endpoint_url`). The similarity-cache probe,
persistence, and tracing in these callers are untouched.

## 5. Testing (TDD — mandatory)

Failing tests first, then minimal code to pass, then refactor.

**Client unit tests** (`tests/services/onechat/test_client.py`), onechat HTTP/SSE
mocked (httpx `MockTransport` or `respx`):

- Each of `chat_v1/v2/v3` posts to the correct derived path, forwards
  `mcp_endpoint_url`, includes `session_id` only when provided, and returns the
  parsed JSON body.
- `stream_v4`/`stream_v5`/`stream_by_version` yield the expected `(name, data)`
  events from a mocked SSE body; `stream_by_version` falls back to v5 on an
  unknown version.
- `health` returns `{"status": "ok"}`.
- Non-200 → `OneChatError` with the upstream status; `ReadTimeout` → 504.

**Migration/regression tests:** existing chat, stream, responses, and
session-warm-up tests must still pass; add assertions that each migrated call
site drives the client with the right version and payload. Update the
`SETTINGS_GROUPS`/config tests for the `ONECHAT_BASE_URL` rename.

## 6. Risks

- **SETTINGS_GROUPS drift** — the rename must land in `config.py`, the group
  list, `.env(.example)`, and their tests together, or the settings UI/tests break.
- **SSE parsing regression** — moving `_parse_sse_block` must preserve the exact
  event/`data:` handling; covered by porting the current stream tests.
- **Stored setting overrides** — old `ONECHAT_V*_URL` DB overrides go inert;
  acceptable, re-entered via admin UI.

## 7. Security note (pre-existing, unrelated)

`spec/agent-onechat.md` contains committed live-looking API keys (OpenRouter,
OpenAI). Rotate and scrub these independently of this work.
