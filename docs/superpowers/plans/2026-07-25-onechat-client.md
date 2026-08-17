# OneChat Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `backend/` a single OneChat transport client covering every `spec/api/` chat endpoint (`v1`–`v5` + `/health`), and migrate the four scattered call sites onto it.

**Architecture:** A new `app/services/onechat/` package owns transport only (payloads, HTTP/SSE, error mapping) and derives every path from one `ONECHAT_BASE_URL`. Business logic — persistence, similarity cache, session warm-up, tracing — stays in the callers. Config replaces the three hardcoded per-endpoint URLs with the base URL.

**Tech Stack:** Python 3, FastAPI, httpx (also the test transport via `httpx.MockTransport`), pytest (`asyncio_mode = "auto"` — `async def test_*` runs directly, no decorator), Tortoise ORM.

## Global Constraints

- Branch: `feat/onechat-client` (already created and checked out).
- TDD mandatory: failing test → confirm fail → minimal code → confirm pass → commit.
- Prefix every shell command with `rtk` (e.g. `rtk pytest ...`, `rtk git commit ...`).
- Google Python style; American English; organized imports sorted by path.
- Client is transport-only: no DB, tracing, or persistence inside `app/services/onechat/`.
- Chat payload is uniform: `{"query", "mcp_endpoint_url", "session_id"}`; omit `session_id` when `None`.
- Out of scope: `/v1/mcp/agencies`, `/v1/mcp/health`; the duplicate `_parse_sse_block` in `app/routers/chat.py` (it parses portal-emitted events, not upstream — leave it).

---

### Task 1: Add `ONECHAT_BASE_URL` to config (additive)

Add the base URL alongside the existing keys so nothing breaks yet; the old keys are removed in Task 7.

**Files:**
- Modify: `backend/app/config.py` (OneChat block ~67-72; `SETTINGS_GROUPS["OneChat"]` line ~156)
- Test: `backend/tests/test_config_onechat_base.py`

**Interfaces:**
- Produces: `settings.ONECHAT_BASE_URL: str` (default `"http://185.84.160.55:8000"`); `"ONECHAT_BASE_URL"` present in `SETTINGS_GROUPS["OneChat"]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config_onechat_base.py
from app.config import SETTINGS_GROUPS, settings


def test_onechat_base_url_default():
    assert settings.ONECHAT_BASE_URL == "http://185.84.160.55:8000"


def test_onechat_base_url_in_settings_group():
    assert "ONECHAT_BASE_URL" in SETTINGS_GROUPS["OneChat"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/test_config_onechat_base.py -v`
Expected: FAIL — `AttributeError: ONECHAT_BASE_URL` / KeyError.

- [ ] **Step 3: Write minimal implementation**

In `app/config.py`, in the OneChat block add:

```python
    ONECHAT_BASE_URL: str = "http://185.84.160.55:8000"
```

In `SETTINGS_GROUPS`, add the key to the OneChat group (keep the existing three for now):

```python
    "OneChat": ["CHAT_STREAM_VERSION", "MCP_ENDPOINT_URL", "ONECHAT_BASE_URL", "ONECHAT_V3_URL", "ONECHAT_V4_URL", "ONECHAT_V5_URL"],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk pytest tests/test_config_onechat_base.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add app/config.py tests/test_config_onechat_base.py
rtk git commit -m "feat(config): add ONECHAT_BASE_URL"
```

---

### Task 2: OneChat client — sync methods, health, error type

**Files:**
- Create: `backend/app/services/onechat/__init__.py`
- Create: `backend/app/services/onechat/client.py`
- Test: `backend/tests/services/onechat/__init__.py` (empty), `backend/tests/services/onechat/test_client_sync.py`

**Interfaces:**
- Consumes: `settings.ONECHAT_BASE_URL`, `settings.EXTERNAL_CHAT_TIMEOUT`.
- Produces:
  - `SseEvent = tuple[str, dict]`
  - `OneChatError(status_code: int, message: str)` (Exception; attributes `status_code`, `message`)
  - `OneChatClient(base_url: str | None = None, *, transport: httpx.AsyncBaseTransport | None = None)`
  - `OneChatClient.chat_v1/chat_v2/chat_v3(query, mcp_endpoint_url, session_id=None) -> dict`
  - `OneChatClient.health() -> dict`
  - `get_client() -> OneChatClient` (production instance, `transport=None`)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/onechat/test_client_sync.py
import httpx
import pytest

from app.services.onechat import OneChatClient, OneChatError


def _transport(recorder: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        recorder["url"] = str(request.url)
        recorder["body"] = httpx.Response  # placeholder, overwritten below
        import json
        recorder["json"] = json.loads(request.content)
        recorder["method"] = request.method
        return httpx.Response(200, json={"data": {"answer": "hi", "session_id": "s1"}})
    return httpx.MockTransport(handler)


async def test_chat_v3_posts_to_derived_path_and_forwards_fields():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_transport(rec))
    out = await client.chat_v3("q", "http://mcp", "conv1")
    assert out == {"data": {"answer": "hi", "session_id": "s1"}}
    assert rec["url"] == "http://oc:8000/v3/chat"
    assert rec["json"] == {"query": "q", "mcp_endpoint_url": "http://mcp", "session_id": "conv1"}


async def test_chat_v1_and_v2_paths():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_transport(rec))
    await client.chat_v1("q", "http://mcp", "c")
    assert rec["url"] == "http://oc:8000/v1/chat"
    await client.chat_v2("q", "http://mcp", "c")
    assert rec["url"] == "http://oc:8000/v2/chat"


async def test_session_id_omitted_when_none():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_transport(rec))
    await client.chat_v3("q", "http://mcp", None)
    assert "session_id" not in rec["json"]


async def test_health_returns_status():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://oc:8000/health"
        assert request.method == "GET"
        return httpx.Response(200, json={"status": "ok"})
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    assert await client.health() == {"status": "ok"}


async def test_non_200_raises_onechat_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    with pytest.raises(OneChatError) as exc:
        await client.chat_v3("q", "http://mcp", "c")
    assert exc.value.status_code == 503
    assert "upstream down" in exc.value.message


async def test_timeout_maps_to_504():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    with pytest.raises(OneChatError) as exc:
        await client.chat_v3("q", "http://mcp", "c")
    assert exc.value.status_code == 504


def test_default_base_url_from_settings():
    from app.config import settings
    assert OneChatClient()._base_url == settings.ONECHAT_BASE_URL.rstrip("/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/services/onechat/test_client_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.onechat`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/onechat/__init__.py
from app.services.onechat.client import (
    OneChatClient,
    OneChatError,
    SseEvent,
    get_client,
)

__all__ = ["OneChatClient", "OneChatError", "SseEvent", "get_client"]
```

```python
# backend/app/services/onechat/client.py
"""Transport-only client for the OneChat service (spec/api/ v1-v5 + health).

Owns payload assembly, HTTP/SSE, and error mapping. No persistence, tracing,
or business logic lives here; callers keep that.
"""
import logging
from typing import AsyncIterator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SseEvent = tuple[str, dict]


class OneChatError(Exception):
    """A non-2xx response or transport failure from onechat."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"OneChat {status_code}: {message}")


def _payload(query: str, mcp_endpoint_url: str, session_id: str | None) -> dict:
    body = {"query": query, "mcp_endpoint_url": mcp_endpoint_url}
    if session_id is not None:
        body["session_id"] = session_id
    return body


class OneChatClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base_url = (base_url or settings.ONECHAT_BASE_URL).rstrip("/")
        self._transport = transport

    def _open(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    async def _post_json(
        self, path: str, query: str, mcp_endpoint_url: str, session_id: str | None
    ) -> dict:
        url = f"{self._base_url}{path}"
        try:
            async with self._open(settings.EXTERNAL_CHAT_TIMEOUT) as client:
                resp = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=_payload(query, mcp_endpoint_url, session_id),
                )
        except httpx.ReadTimeout as e:
            raise OneChatError(504, f"onechat {path} timed out") from e
        except httpx.HTTPError as e:
            raise OneChatError(502, f"onechat {path} transport error: {e}") from e
        if resp.status_code != 200:
            raise OneChatError(resp.status_code, resp.text[:200])
        return resp.json()

    async def chat_v1(self, query, mcp_endpoint_url, session_id=None) -> dict:
        return await self._post_json("/v1/chat", query, mcp_endpoint_url, session_id)

    async def chat_v2(self, query, mcp_endpoint_url, session_id=None) -> dict:
        return await self._post_json("/v2/chat", query, mcp_endpoint_url, session_id)

    async def chat_v3(self, query, mcp_endpoint_url, session_id=None) -> dict:
        return await self._post_json("/v3/chat", query, mcp_endpoint_url, session_id)

    async def health(self) -> dict:
        url = f"{self._base_url}/health"
        try:
            async with self._open(settings.EXTERNAL_CHAT_TIMEOUT) as client:
                resp = await client.get(url)
        except httpx.HTTPError as e:
            raise OneChatError(502, f"onechat /health transport error: {e}") from e
        if resp.status_code != 200:
            raise OneChatError(resp.status_code, resp.text[:200])
        return resp.json()


def get_client() -> OneChatClient:
    return OneChatClient()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk pytest tests/services/onechat/test_client_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add app/services/onechat tests/services/onechat
rtk git commit -m "feat(onechat): transport client sync methods + health"
```

---

### Task 3: OneChat client — streaming (v4/v5) + SSE parsing

**Files:**
- Modify: `backend/app/services/onechat/client.py`
- Test: `backend/tests/services/onechat/test_client_stream.py`

**Interfaces:**
- Consumes: `settings.V4_STREAM_TIMEOUT`.
- Produces:
  - `OneChatClient.stream_v4/stream_v5(query, mcp_endpoint_url, session_id=None) -> AsyncIterator[SseEvent]`
  - `OneChatClient.stream_by_version(version: str, query, mcp_endpoint_url, session_id=None) -> AsyncIterator[SseEvent]` (unknown version → v5 with a warning)
  - `parse_sse_block(block: str) -> SseEvent | None` (module-level; event name defaults to `"message"`, returns `None` when no `data:` line or bad JSON)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/onechat/test_client_stream.py
import httpx
import pytest

from app.services.onechat import OneChatClient, OneChatError
from app.services.onechat.client import parse_sse_block

SSE_BODY = (
    "event: status\ndata: {\"stage\": \"routing\"}\n\n"
    "event: answer\ndata: {\"answer\": \"final\"}\n\n"
    "event: done\ndata: {\"session_id\": \"s1\", \"total_ms\": 12}\n\n"
)


def _sse_transport(recorder: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        recorder["url"] = str(request.url)
        if status != 200:
            return httpx.Response(status, text="boom")
        return httpx.Response(200, text=SSE_BODY)
    return httpx.MockTransport(handler)


def test_parse_sse_block():
    assert parse_sse_block("event: answer\ndata: {\"answer\": \"x\"}") == ("answer", {"answer": "x"})
    assert parse_sse_block("data: {\"a\": 1}") == ("message", {"a": 1})
    assert parse_sse_block("event: ping\n(no data)") is None
    assert parse_sse_block("data: not-json") is None


async def test_stream_v5_yields_events_in_order():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec))
    events = [ev async for ev in client.stream_v5("q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v5/chat"
    assert events == [
        ("status", {"stage": "routing"}),
        ("answer", {"answer": "final"}),
        ("done", {"session_id": "s1", "total_ms": 12}),
    ]


async def test_stream_by_version_selects_v4():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec))
    _ = [ev async for ev in client.stream_by_version("v4", "q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v4/chat"


async def test_stream_by_version_unknown_falls_back_to_v5():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec))
    _ = [ev async for ev in client.stream_by_version("bogus", "q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v5/chat"


async def test_stream_non_200_raises_onechat_error():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec, status=500))
    with pytest.raises(OneChatError) as exc:
        _ = [ev async for ev in client.stream_v5("q", "http://mcp", "c")]
    assert exc.value.status_code == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/services/onechat/test_client_stream.py -v`
Expected: FAIL — `ImportError: parse_sse_block` / `AttributeError: stream_v5`.

- [ ] **Step 3: Write minimal implementation**

Add to `app/services/onechat/client.py` (module-level `parse_sse_block`, and methods on `OneChatClient`):

```python
import json


def parse_sse_block(block: str) -> SseEvent | None:
    event_name = "message"
    data_line = None
    for line in block.strip().split("\n"):
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_line = line[5:].strip()
    if not data_line:
        return None
    try:
        return event_name, json.loads(data_line)
    except json.JSONDecodeError:
        return None
```

```python
    # methods on OneChatClient
    async def stream_v4(self, query, mcp_endpoint_url, session_id=None):
        async for ev in self._stream("/v4/chat", query, mcp_endpoint_url, session_id):
            yield ev

    async def stream_v5(self, query, mcp_endpoint_url, session_id=None):
        async for ev in self._stream("/v5/chat", query, mcp_endpoint_url, session_id):
            yield ev

    def stream_by_version(self, version, query, mcp_endpoint_url, session_id=None):
        v = (version or "").strip().lower()
        if v == "v4":
            return self.stream_v4(query, mcp_endpoint_url, session_id)
        if v != "v5":
            logger.warning("Unknown OneChat stream version %r — falling back to v5", version)
        return self.stream_v5(query, mcp_endpoint_url, session_id)

    async def _stream(self, path, query, mcp_endpoint_url, session_id):
        url = f"{self._base_url}{path}"
        try:
            async with self._open(settings.V4_STREAM_TIMEOUT) as client:
                async with client.stream(
                    "POST", url,
                    headers={"Content-Type": "application/json"},
                    json=_payload(query, mcp_endpoint_url, session_id),
                ) as resp:
                    if resp.status_code != 200:
                        body = ""
                        try:
                            body = (await resp.aread()).decode()[:200]
                        except Exception:
                            pass
                        raise OneChatError(resp.status_code, body)
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            block, buffer = buffer.split("\n\n", 1)
                            parsed = parse_sse_block(block)
                            if parsed is not None:
                                yield parsed
        except httpx.ReadTimeout as e:
            raise OneChatError(504, f"onechat {path} timed out") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk pytest tests/services/onechat/test_client_stream.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add app/services/onechat/client.py tests/services/onechat/test_client_stream.py
rtk git commit -m "feat(onechat): streaming v4/v5 + SSE parsing"
```

---

### Task 4: Migrate `ensure_session_warmed` onto the client

`ensure_session_warmed` drops its `onechat_url` parameter and uses `chat_v3` internally; all three callers drop the URL argument.

**Files:**
- Modify: `backend/app/services/session.py` (whole function)
- Modify: `backend/app/services/chat/stream.py:106`
- Modify: `backend/app/routers/chat.py:96`
- Modify: `backend/app/services/responses/session.py:89`
- Test: `backend/tests/services/test_session_warm.py`

**Interfaces:**
- Consumes: `get_client()`, `OneChatClient.chat_v3`.
- Produces: `ensure_session_warmed(conversation, mcp_endpoint_url, *, client: OneChatClient | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_session_warm.py
import httpx

from app.models.conversation import Conversation, Message
from app.services.onechat import OneChatClient
from app.services.session import ensure_session_warmed


async def test_warm_up_uses_chat_v3_and_stores_session_id():
    conv = await Conversation.create(title="t")
    await Message.create(conversation_id=conv.id, role="user", content="hello")

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"session_id": "ext-1"}})

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await ensure_session_warmed(conv, "http://mcp", client=client)

    assert seen["url"] == "http://oc:8000/v3/chat"
    refreshed = await Conversation.get(id=conv.id)
    assert refreshed.external_session_id == "ext-1"


async def test_warm_up_noop_when_already_warmed():
    conv = await Conversation.create(title="t", external_session_id="already")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await ensure_session_warmed(conv, "http://mcp", client=client)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/services/test_session_warm.py -v`
Expected: FAIL — `TypeError` (old signature / unexpected `client` kwarg).

- [ ] **Step 3: Write minimal implementation**

Rewrite `app/services/session.py`:

```python
from opentelemetry import trace

from app.models.conversation import Conversation, Message
from app.services.onechat import OneChatClient, get_client

tracer = trace.get_tracer(__name__)


async def ensure_session_warmed(
    conversation: Conversation,
    mcp_endpoint_url: str,
    *,
    client: OneChatClient | None = None,
) -> None:
    with tracer.start_as_current_span("chat_stream_endpoint") as span:
        if conversation.external_session_id is not None:
            span.set_attribute("session_already_warmed", True)
            return

        first_msg = (
            await Message.filter(conversation_id=conversation.id, role="user")
            .order_by("created_at")
            .first()
        )
        if first_msg is None:
            span.set_attribute("no_first_message", True)
            return

        span.set_attribute("warming_session_for_conversation", str(conversation.id))
        span.set_attribute("query", first_msg.content)

        try:
            oc = client or get_client()
            body = await oc.chat_v3(first_msg.content, mcp_endpoint_url, str(conversation.id))
            data = body.get("data", {})
            conversation.external_session_id = data.get("session_id") or str(conversation.id)
            span.set_attribute("warmed_session_id", conversation.external_session_id)
        except Exception as e:
            span.set_status(trace.StatusCode.ERROR, f"Session warm-up failed: {str(e)}")
            span.set_attributes({"error": "Session warm-up failed", "exception": str(e)})
            raise e

        try:
            await conversation.save(update_fields=["external_session_id"])
        except Exception as e:
            span.set_status(trace.StatusCode.ERROR, f"Failed to save warmed session: {str(e)}")
            span.set_attributes({"error": "Failed to save warmed session", "exception": str(e)})
            raise e
```

Update the three callers to drop the URL argument:

- `app/services/chat/stream.py:106` →
  `await ensure_session_warmed(conv, settings.MCP_ENDPOINT_URL)`
- `app/routers/chat.py:96` →
  `await ensure_session_warmed(conv, settings.MCP_ENDPOINT_URL)`
- `app/services/responses/session.py:89` — change the call from
  `ensure_session_warmed(conv, settings.ONECHAT_V3_URL, settings.MCP_ENDPOINT_URL)` to
  `ensure_session_warmed(conv, settings.MCP_ENDPOINT_URL)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/services/test_session_warm.py tests/services/responses -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add app/services/session.py app/services/chat/stream.py app/routers/chat.py app/services/responses/session.py tests/services/test_session_warm.py
rtk git commit -m "refactor(onechat): warm sessions via client.chat_v3"
```

---

### Task 5: Migrate the v3 sync route (`chat_external`) onto the client

**Files:**
- Modify: `backend/app/routers/chat.py` (`chat_external`, ~53-163: the `httpx.AsyncClient` block ~100-107)
- Test: `backend/tests/routers/test_chat_external_client.py`

**Interfaces:**
- Consumes: `get_client()`, `OneChatClient.chat_v3`, `OneChatError`.
- Produces: no new symbols; behavior preserved (still returns `ChatResponse`, still `502` on upstream failure).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/routers/test_chat_external_client.py
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tortoise import Tortoise
from contextlib import asynccontextmanager

from app.errors import register_error_handlers
from app.routers import chat as chat_router
from app.services.onechat import OneChatClient


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


def _app() -> FastAPI:
    app = FastAPI(lifespan=_lifespan)
    register_error_handlers(app)
    app.include_router(chat_router.router, prefix="/api/v1")
    return app


def test_chat_external_calls_v3_via_client():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"answer": "A", "sections": [], "session_id": "s"}})

    fake = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    with patch.object(chat_router, "get_client", lambda: fake):
        with TestClient(_app()) as tc:
            r = tc.post("/api/v1/chat", json={"query": "hello"})
    assert r.status_code == 200
    assert r.json()["data"]["answer"] == "A"
    assert seen["url"] == "http://oc:8000/v3/chat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/routers/test_chat_external_client.py -v`
Expected: FAIL — `chat_router` has no `get_client` / still hits real URL.

- [ ] **Step 3: Write minimal implementation**

In `app/routers/chat.py`:

1. Add import near the other service imports:
   `from app.services.onechat import OneChatError, get_client`
2. Replace the timed `httpx.AsyncClient` block (currently ~100-107 building `payload` and posting to `settings.ONECHAT_V3_URL`, plus the `if resp.status_code != 200` guard ~109-111) with:

```python
        payload = {"query": query, "mcp_endpoint_url": settings.MCP_ENDPOINT_URL, "session_id": conversation_id}
        start_time_ns = time.perf_counter_ns()
        try:
            raw_data = await get_client().chat_v3(query, settings.MCP_ENDPOINT_URL, conversation_id)
        except OneChatError as e:
            span.set_status(StatusCode.ERROR, f"External chat request failed with status {e.status_code}")
            raise HTTPException(status_code=502, detail="Failed to get response from external chat service")
        end_time_ns = time.perf_counter_ns()
        response_time = int((end_time_ns - start_time_ns) // 1_000_000)
```

Then delete the now-redundant `raw_data = resp.json()` and `response_time` lines that followed the old block, and the `span.set_attributes({"external_response": resp.text})` line (there is no `resp` now — replace with `span.set_attribute("external_response", json.dumps(raw_data, ensure_ascii=False))`). The rest of the handler (`data = raw_data.get("data", {})` onward) is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/routers/test_chat_external_client.py tests/routers/test_chat_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add app/routers/chat.py tests/routers/test_chat_external_client.py
rtk git commit -m "refactor(onechat): v3 sync route via client.chat_v3"
```

---

### Task 6: Migrate the streaming path (`stream.py`) + responses resolution

`_stream_live` uses the client generator; `_stream_upstream` becomes `_stream_version` (version only); `TurnPlan.upstream_url` is removed; `responses.py` and `request.py` follow.

**Files:**
- Modify: `backend/app/services/chat/stream.py` (`_stream_upstream`, `TurnPlan`, `prepare_turn`, `_stream_live`; drop local `_parse_sse_block`)
- Modify: `backend/app/routers/responses.py` (~73-78: the `plan.upstream_url = ...` block)
- Modify: `backend/app/services/responses/request.py` (import + `resolve_model`)
- Test: `backend/tests/routers/test_chat_stream_upstream.py` (update to the new upstream seam)

**Interfaces:**
- Consumes: `OneChatClient.stream_by_version`, `OneChatError`, `get_client`.
- Produces:
  - `_stream_version() -> str` (replaces `_stream_upstream() -> tuple[str, str]`)
  - `TurnPlan` without `upstream_url`.

- [ ] **Step 1: Write the failing test**

Add to `tests/routers/test_chat_stream_upstream.py` a test that drives the ASGI stream with a mocked client (the existing `_FakeStream`/`_FakeResponse` scaffolding patches `httpx.AsyncClient`; keep those characterization tests but add one asserting the new seam):

```python
def test_stream_version_resolves_without_url(monkeypatch):
    from app.services.chat import stream as turn_stream
    monkeypatch.setattr(turn_stream.settings, "CHAT_STREAM_VERSION", "v4")
    assert turn_stream._stream_version() == "v4"
    monkeypatch.setattr(turn_stream.settings, "CHAT_STREAM_VERSION", "bogus")
    assert turn_stream._stream_version() == "v5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/routers/test_chat_stream_upstream.py::test_stream_version_resolves_without_url -v`
Expected: FAIL — `_stream_version` does not exist.

- [ ] **Step 3: Write minimal implementation**

In `app/services/chat/stream.py`:

1. Add import: `from app.services.onechat import OneChatError, get_client`.
2. Replace `_stream_upstream` with:

```python
def _stream_version() -> str:
    """Resolve the streaming version from CHAT_STREAM_VERSION (unknown → v5)."""
    version = (settings.CHAT_STREAM_VERSION or "").strip().lower()
    if version == "v4":
        return "v4"
    if version != "v5":
        logger.warning("Unknown CHAT_STREAM_VERSION %r — falling back to v5", settings.CHAT_STREAM_VERSION)
    return "v5"
```

3. In `TurnPlan`, remove the `upstream_url: str` field.
4. In `prepare_turn`, replace `stream_version, upstream_url = _stream_upstream()` with `stream_version = _stream_version()` and drop `upstream_url=upstream_url` from the `TurnPlan(...)` construction.
5. In `_stream_live`, replace the whole `try: async with httpx.AsyncClient(...) ... except httpx.ReadTimeout ... except Exception ...` transport block with a client-driven loop that preserves today's event output:

```python
    version = plan.stream_version
    try:
        async for event_name, event_data in get_client().stream_by_version(
            version, plan.query, settings.MCP_ENDPOINT_URL, plan.conversation_id
        ):
            if log_latency_ms == 0:
                log_latency_ms = int((time.perf_counter_ns() - start_ns) // 1_000_000)
            if event_name == "answer":
                answer_data = event_data
            elif event_name == "done":
                session_id = event_data.get("session_id")
                total_ms = event_data.get("total_ms")
                thread_name = event_data.get("thread_name")
                done_event_data = event_data
            with tracer.start_as_current_span("event") as event_span:
                event_span.set_attribute("stream_event", event_name)
                event_span.set_attribute("event_data", json.dumps(event_data)[:500])
            if event_name != "done":
                yield ChatEvent(event_name, event_data)
    except OneChatError as e:
        msg = (
            f"OneChat {version} connection timed out"
            if e.status_code == 504
            else f"OneChat {version} returned {e.status_code}: {e.message}"
        )
        yield ChatEvent("error", {"message": msg, "code": e.status_code})
        yield ChatEvent("done", {"session_id": plan.conversation_id, "total_ms": 0})
        return
    except Exception as e:
        yield ChatEvent("error", {"message": str(e), "code": 500})
        yield ChatEvent("done", {"session_id": plan.conversation_id, "total_ms": 0})
        return
```

6. Delete the now-unused local `_parse_sse_block` in `stream.py` and the `import httpx` if no longer referenced there.

In `app/routers/responses.py`, replace the version-pin block:

```python
    if plan.stream_version != stream_version:
        plan.stream_version = stream_version
```

(remove the `plan.upstream_url = ...` assignment entirely.)

In `app/services/responses/request.py`, change the import `from app.services.chat.stream import _stream_upstream` to `_stream_version`, and in `resolve_model` replace `version, _url = _stream_upstream()` with `version = _stream_version()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/routers/test_chat_stream_upstream.py tests/routers/test_chat_stream_message_id.py tests/services/responses -v`
Expected: PASS. If a characterization test in `test_chat_stream_upstream.py` patched `httpx.AsyncClient` directly, repoint it to patch `app.services.chat.stream.get_client` returning an `OneChatClient` with a `MockTransport` (same SSE bodies).

- [ ] **Step 5: Commit**

```bash
rtk git add app/services/chat/stream.py app/routers/responses.py app/services/responses/request.py tests/routers/test_chat_stream_upstream.py
rtk git commit -m "refactor(onechat): streaming path via client.stream_by_version"
```

---

### Task 7: Remove the legacy per-endpoint URL settings

Now that nothing references them, delete `ONECHAT_V3_URL/V4_URL/V5_URL`.

**Files:**
- Modify: `backend/app/config.py` (OneChat block + `SETTINGS_GROUPS["OneChat"]`)
- Modify: `backend/.env`, `backend/.env.example` (if the keys appear)
- Test: `backend/tests/test_config_onechat_base.py` (extend)

**Interfaces:**
- Produces: `SETTINGS_GROUPS["OneChat"] == ["CHAT_STREAM_VERSION", "MCP_ENDPOINT_URL", "ONECHAT_BASE_URL"]`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_onechat_base.py`:

```python
def test_legacy_onechat_urls_removed():
    from app import config
    assert not hasattr(config.settings, "ONECHAT_V3_URL")
    assert "ONECHAT_V3_URL" not in config.SETTINGS_GROUPS["OneChat"]
    assert config.SETTINGS_GROUPS["OneChat"] == [
        "CHAT_STREAM_VERSION", "MCP_ENDPOINT_URL", "ONECHAT_BASE_URL",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/test_config_onechat_base.py::test_legacy_onechat_urls_removed -v`
Expected: FAIL — attribute/list still present.

- [ ] **Step 3: Confirm no code references remain, then implement**

```bash
rtk grep "ONECHAT_V[345]_URL" app
```

Expected: no matches in `app/` (tests may still reference in fixtures — update those too). Then in `app/config.py` delete the three `ONECHAT_V3_URL/V4_URL/V5_URL` lines and trim `SETTINGS_GROUPS["OneChat"]` to:

```python
    "OneChat": ["CHAT_STREAM_VERSION", "MCP_ENDPOINT_URL", "ONECHAT_BASE_URL"],
```

Remove the three keys from `backend/.env` and `backend/.env.example` if present; ensure `ONECHAT_BASE_URL` is documented there.

- [ ] **Step 4: Run the full backend suite**

Run: `rtk pytest -q`
Expected: PASS (no reference to the removed settings anywhere).

- [ ] **Step 5: Commit**

```bash
rtk git add app/config.py .env.example tests/test_config_onechat_base.py
rtk git commit -m "refactor(config): drop legacy ONECHAT_V3/V4/V5_URL"
```

---

## Post-plan wrap-up (orchestrator, after all tasks green)

- [ ] Update `CONTEXT.md` and commit (project rule).
- [ ] Open PR `feat/onechat-client` → `dev`.
- [ ] (Separate, unrelated) rotate/scrub the committed API keys in `spec/agent-onechat.md`.

## Self-Review

- **Spec coverage:** §2 interface → Tasks 2-3; §3 config `ONECHAT_BASE_URL` → Tasks 1 & 7; §4 call-site migration table → Tasks 4 (session ×3 callers), 5 (v3 route), 6 (stream + responses + request); §5 testing → tests in every task; §6 risks (SETTINGS_GROUPS drift, SSE regression, stored overrides) → Tasks 1/7 lockstep + Task 6 SSE tests. All covered.
- **Placeholder scan:** every code step has concrete code; no TBD/TODO.
- **Type consistency:** `OneChatClient`, `OneChatError(status_code, message)`, `SseEvent`, `get_client`, `parse_sse_block`, `stream_by_version`, `_stream_version`, `ensure_session_warmed(conversation, mcp_endpoint_url, *, client=None)` used identically across Tasks 2-7.
