# Unified Chat Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the three chat routes into one `/chat` path served over HTTP JSON, SSE, and WebSocket — all driven by the existing `run_turn` core — with OneChat version (v1–v5) selectable via an OpenAI-style `model` field.

**Architecture:** `POST /chat` is one handler: it runs `prepare_turn` then either drains `run_turn` into a JSON envelope (`stream=false`) or streams SSE (`stream=true`). `WS /chat` is a second handler on the same path (ASGI dispatches HTTP vs WebSocket by scope type), mirroring `responses.py`. A `model` string maps to a OneChat version via a small resolver; the version threads through `prepare_turn(requested_version=...)`. The pipeline already normalizes every version, so no pipeline changes are needed.

**Tech Stack:** Python 3.12, FastAPI/Starlette, httpx, Tortoise ORM, pytest; frontend React + TypeScript, Vitest.

## Global Constraints

- TDD is mandatory: failing test → confirm fail → minimal code → confirm pass → commit. One behavior per test.
- Google style guides (Python/TS). Clean, minimal code; organized imports sorted by path.
- American English naming; avoid `xxxList` plural names.
- Prefix every shell command with `rtk` (including inside `&&` chains).
- Backend tests: `cd backend && rtk pytest <path> -v`. Frontend tests: `cd frontend && rtk vitest run <path>`.
- Hard cutover: `/chat/external` and `/chat/stream` are removed; the frontend migrates in the same branch. No deprecated shims.
- Model → version mapping (exact): `model` omitted / `null` / `"onechat"` → `v5`; `"onechat-v1"`…`"onechat-v5"` → `v1`…`v5`; anything else (typo/unknown, including bare `"v3"`) → `v5` (lenient).
- Sync JSON envelope is **version-faithful passthrough**: `data` = the version's `answer`-event payload merged with `message_id`, `cached`, `agentSteps`; top level adds `success`, `conversation_id`, `responseTime`.
- WebSocket: header-bearer auth only (no query token), connection cap, per-connection deadline, one turn in flight at a time.
- Branch: `feat/unified-chat-endpoint` (already created).

---

## File Structure

**Create:**
- `backend/app/services/chat/model.py` — `resolve_model_version(model) -> str`.
- `backend/app/services/chat/aggregate.py` — `TurnResult` dataclass + `collect_turn(plan, *, background_tasks) -> TurnResult`.
- `backend/app/services/chat/ws.py` — `ConnectionRegistry`, `bearer_user`, `handle_chat_frame`, `Send` (transport-free WS logic).
- `backend/tests/services/chat/test_model_version.py`
- `backend/tests/services/chat/test_aggregate.py`
- `backend/tests/routers/test_chat_unified.py` — POST JSON/SSE + version selection.
- `backend/tests/routers/test_chat_ws.py` — WebSocket.

**Modify:**
- `backend/app/schemas/chat.py` — add `stream`, `model` to `ChatRequest`.
- `backend/app/config.py:82` — add `CHAT_WS_MAX_CONNECTIONS`, `CHAT_WS_MAX_DURATION_SECONDS`.
- `backend/app/routers/chat.py` — full rewrite to the merged surface.
- `frontend/src/features/chat/chatApi.ts` — single endpoint + new envelope type.
- `frontend/src/features/chat/useChat.ts:99-124` — map the new sync envelope.
- `frontend/src/features/agencies/agencyApi.ts` — read the new envelope.

**Delete / rewrite tests bound to removed routes:**
- `backend/tests/routers/test_chat_external_client.py` (delete)
- `backend/tests/routers/test_chat_cache.py` (rewrite against unified JSON)
- `backend/tests/routers/test_chat_stream_message_id.py` (rewrite calls to `chat(..., stream=True)`)
- `backend/tests/routers/test_chat_stream_agent_steps.py`, `test_chat_stream_upstream.py`, `test_chat_stream_v5_fields.py` (rewrite handler calls; pipeline assertions unchanged)
- `backend/tests/services/test_chat_turn.py` (remove `_copy_cached_answer` test)
- `backend/tests/test_surface_parity.py:76` (drop the `/chat/stream` entry)
- `frontend/src/features/chat/chatApi.test.ts` (update endpoint URL/shape)

---

## Task 1: Model → version resolver

**Files:**
- Create: `backend/app/services/chat/model.py`
- Test: `backend/tests/services/chat/test_model_version.py`

**Interfaces:**
- Consumes: `resolve_version` from `app.services.onechat` (`resolve_version(requested: str | None) -> str`, returns `v5` for absent/invalid).
- Produces: `resolve_model_version(model: str | None) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/chat/test_model_version.py
import pytest

from app.services.chat.model import resolve_model_version


@pytest.mark.parametrize("model,expected", [
    (None, "v5"),
    ("", "v5"),
    ("onechat", "v5"),
    ("ONECHAT", "v5"),
    ("onechat-v1", "v1"),
    ("onechat-v3", "v3"),
    ("onechat-v5", "v5"),
    ("onechat-v9", "v5"),   # unknown suffix -> lenient v5
    ("v3", "v5"),           # bare, not in the onechat- scheme -> v5
    ("garbage", "v5"),
])
def test_resolve_model_version(model, expected):
    assert resolve_model_version(model) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && rtk pytest tests/services/chat/test_model_version.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.chat.model`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/chat/model.py
"""Map the public `model` id to a OneChat upstream version.

OpenAI-style: `onechat` (or absent) means newest; `onechat-vN` pins a version.
Anything unrecognized falls back to newest, matching resolve_version()'s lenient
contract so a typo degrades instead of erroring.
"""
from app.services.onechat import resolve_version

_PREFIX = "onechat-"


def resolve_model_version(model: str | None) -> str:
    m = (model or "").strip().lower()
    suffix = m[len(_PREFIX):] if m.startswith(_PREFIX) else ""
    return resolve_version(suffix)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && rtk pytest tests/services/chat/test_model_version.py -v`
Expected: PASS (10 cases).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/chat/model.py backend/tests/services/chat/test_model_version.py
rtk git commit -m "feat: model->OneChat version resolver for unified chat"
```

---

## Task 2: Sync aggregator (`collect_turn`)

**Files:**
- Create: `backend/app/services/chat/aggregate.py`
- Test: `backend/tests/services/chat/test_aggregate.py`

**Interfaces:**
- Consumes: `run_turn`, `TurnPlan` from `app.services.chat.stream`; `build_pipeline_snapshot(events: list[tuple[str, dict]], errors: list) -> dict | list` from `app.services.chat.pipeline_snapshot`.
- Produces:
  - `TurnResult` dataclass: `answer_data: dict`, `agent_steps: dict | list`, `message_id: str`, `total_ms: int`, `cached: bool`, `error: dict | None`.
  - `async collect_turn(plan: TurnPlan, *, background_tasks: BackgroundTasks | None) -> TurnResult`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/chat/test_aggregate.py
from unittest.mock import patch

import pytest

from app.services.chat import aggregate as agg
from app.services.chat.aggregate import collect_turn
from app.services.chat.stream import ChatEvent, TurnPlan
from app.utils import generate_uuid


def _plan() -> TurnPlan:
    return TurnPlan(query="q", conversation_id="c1", user=None,
                    stream_version="v5", assistant_message_id=generate_uuid())


def _fake_run_turn(*events):
    async def gen(plan, *, background_tasks=None):
        for e in events:
            yield e
    return gen


@pytest.mark.asyncio
async def test_collect_turn_folds_answer_steps_and_done():
    events = [
        ChatEvent("step", {"name": "discover", "status": "done"}),
        ChatEvent("answer", {"answer": "A", "summary": "S", "sections": [], "errors": []}),
        ChatEvent("done", {"session_id": "c1", "total_ms": 1234, "message_id": "msg-1"}),
    ]
    with patch.object(agg, "run_turn", _fake_run_turn(*events)):
        result = await collect_turn(_plan(), background_tasks=None)
    assert result.answer_data["answer"] == "A"
    assert result.answer_data["summary"] == "S"
    assert result.message_id == "msg-1"
    assert result.total_ms == 1234
    assert result.error is None
    assert result.cached is False


@pytest.mark.asyncio
async def test_collect_turn_captures_error_event():
    events = [
        ChatEvent("error", {"message": "boom", "code": 502}),
        ChatEvent("done", {"session_id": "c1", "total_ms": 0}),
    ]
    with patch.object(agg, "run_turn", _fake_run_turn(*events)):
        result = await collect_turn(_plan(), background_tasks=None)
    assert result.error == {"message": "boom", "code": 502}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && rtk pytest tests/services/chat/test_aggregate.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.chat.aggregate`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/chat/aggregate.py
"""Drain the streaming turn pipeline into a single JSON result.

The sync transport reuses run_turn (so persistence, caching, and classification
stay identical to the stream path) and folds its events into a version-faithful
payload.
"""
from dataclasses import dataclass

from fastapi import BackgroundTasks

from app.services.chat.pipeline_snapshot import build_pipeline_snapshot
from app.services.chat.stream import TurnPlan, run_turn

_PIPELINE_EVENTS = ("step", "agency_start", "agency_responded", "agency_verified")


@dataclass
class TurnResult:
    answer_data: dict
    agent_steps: dict | list
    message_id: str
    total_ms: int
    cached: bool
    error: dict | None


async def collect_turn(
    plan: TurnPlan, *, background_tasks: BackgroundTasks | None
) -> TurnResult:
    answer_data: dict = {}
    pipeline_events: list[tuple[str, dict]] = []
    message_id = str(plan.assistant_message_id)
    total_ms = 0
    error: dict | None = None

    async for event in run_turn(plan, background_tasks=background_tasks):
        if event.name == "answer":
            answer_data = event.data
        elif event.name in _PIPELINE_EVENTS:
            pipeline_events.append((event.name, event.data))
        elif event.name == "done":
            message_id = event.data.get("message_id", message_id)
            total_ms = event.data.get("total_ms") or 0
        elif event.name == "error":
            error = event.data

    return TurnResult(
        answer_data=answer_data,
        agent_steps=build_pipeline_snapshot(pipeline_events, answer_data.get("errors", [])),
        message_id=message_id,
        total_ms=total_ms,
        cached=plan.cached is not None,
        error=error,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && rtk pytest tests/services/chat/test_aggregate.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/chat/aggregate.py backend/tests/services/chat/test_aggregate.py
rtk git commit -m "feat: collect_turn aggregator for sync chat responses"
```

---

## Task 3: Request schema fields

**Files:**
- Modify: `backend/app/schemas/chat.py:6-8`
- Test: `backend/tests/test_chat_schema.py` (add a case)

**Interfaces:**
- Produces: `ChatRequest.stream: bool = False`, `ChatRequest.model: str | None = None`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_chat_schema.py
from app.schemas.chat import ChatRequest


def test_chat_request_stream_and_model_defaults():
    r = ChatRequest(query="q")
    assert r.stream is False
    assert r.model is None
    r2 = ChatRequest(query="q", stream=True, model="onechat-v3")
    assert r2.stream is True
    assert r2.model == "onechat-v3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && rtk pytest tests/test_chat_schema.py::test_chat_request_stream_and_model_defaults -v`
Expected: FAIL — `TypeError`/`ValidationError` (unknown field `stream`).

- [ ] **Step 3: Write minimal implementation**

Edit `backend/app/schemas/chat.py` so `ChatRequest` reads:

```python
class ChatRequest(BaseModel):
    query: str
    conversation_id: str | None = None
    stream: bool = False
    model: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && rtk pytest tests/test_chat_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/chat.py backend/tests/test_chat_schema.py
rtk git commit -m "feat: add stream and model fields to ChatRequest"
```

---

## Task 4: Merged `POST /chat` (JSON + SSE), delete old HTTP routes

**Files:**
- Modify: `backend/app/routers/chat.py` (rewrite the HTTP surface; keep WS for Task 5)
- Test: `backend/tests/routers/test_chat_unified.py`
- Rewrite: `backend/tests/routers/test_chat_stream_message_id.py`, `test_chat_stream_agent_steps.py`, `test_chat_stream_upstream.py`, `test_chat_stream_v5_fields.py`, `test_chat_cache.py`
- Delete: `backend/tests/routers/test_chat_external_client.py`

**Interfaces:**
- Consumes: `resolve_model_version` (Task 1), `collect_turn`/`TurnResult` (Task 2), `ChatRequest.stream`/`.model` (Task 3), `prepare_turn`/`run_turn`/`ConversationNotFound` from `app.services.chat.stream`.
- Produces: `chat(body, background_tasks, user)` at `POST ""`. JSON envelope `{"success", "data": {"message_id","cached","agentSteps", **answer_data}, "conversation_id", "responseTime"}`; error envelope `{"success": False, "error", "conversation_id", "responseTime"}`. `_sse_event` and the `_stream_version` re-export are retained.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/routers/test_chat_unified.py
"""Merged POST /chat: JSON by default, SSE when stream=true, model picks version."""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks

from app.routers import chat as chat_router
from app.schemas.chat import ChatRequest
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent


def _events():
    return [
        ChatEvent("step", {"name": "discover", "status": "done"}),
        ChatEvent("answer", {"answer": "คำตอบ", "summary": "S", "sections": [],
                             "references": [], "errors": []}),
        ChatEvent("done", {"session_id": "c1", "total_ms": 42, "message_id": "m-1"}),
    ]


def _fake_run_turn(*events):
    async def gen(plan, *, background_tasks=None):
        for e in events:
            yield e
    return gen


@pytest.mark.asyncio
async def test_json_response_default(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(chat_router, "run_turn", _fake_run_turn(*_events())), \
         patch("app.services.chat.aggregate.run_turn", _fake_run_turn(*_events())):
        result = await chat_router.chat(ChatRequest(query="q"), BackgroundTasks(), None)
    assert result["success"] is True
    assert result["data"]["answer"] == "คำตอบ"
    assert result["data"]["summary"] == "S"
    assert result["data"]["message_id"] == "m-1"
    assert result["data"]["cached"] is False
    assert result["responseTime"] == 42


@pytest.mark.asyncio
async def test_sse_response_when_stream_true(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(chat_router, "run_turn", _fake_run_turn(*_events())):
        resp = await chat_router.chat(ChatRequest(query="q", stream=True), BackgroundTasks(), None)
        chunks = [c async for c in resp.body_iterator]
    text = "".join(c if isinstance(c, str) else c.decode() for c in chunks)
    assert resp.media_type == "text/event-stream"
    assert "event: answer" in text
    assert "event: done" in text


@pytest.mark.asyncio
async def test_empty_query_is_400(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await chat_router.chat(ChatRequest(query="   "), BackgroundTasks(), None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_model_selects_version_v3(db):
    captured = {}

    async def fake_prepare(*, query, conversation_id, user, is_continuation, requested_version=None):
        captured["version"] = requested_version
        from app.services.chat.stream import TurnPlan
        from app.utils import generate_uuid
        return TurnPlan(query=query, conversation_id=conversation_id, user=user,
                        stream_version=requested_version, assistant_message_id=generate_uuid())

    with patch.object(chat_router, "prepare_turn", fake_prepare), \
         patch.object(chat_router, "run_turn", _fake_run_turn(*_events())), \
         patch("app.services.chat.aggregate.run_turn", _fake_run_turn(*_events())):
        await chat_router.chat(ChatRequest(query="q", model="onechat-v3"), BackgroundTasks(), None)
    assert captured["version"] == "v3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && rtk pytest tests/routers/test_chat_unified.py -v`
Expected: FAIL — `chat_router.chat` has the old delegating signature / missing behavior.

- [ ] **Step 3: Rewrite `chat.py` HTTP surface**

Replace the module's HTTP endpoints (`chat_external`, `chat_stream`, `chat`) and remove `_copy_cached_answer`, `_parse_sse_block`. Keep the imports actually used. New content for the HTTP portion:

```python
import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from app.auth.dependencies import get_current_user_optional
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.chat.aggregate import collect_turn
from app.services.chat.model import resolve_model_version
from app.services.chat.stream import (
    ConversationNotFound,
    _stream_version,  # re-exported: tests/routers/test_chat_stream_version.py imports it from here
    prepare_turn,
    run_turn,
)
from app.utils import generate_uuid

router = APIRouter(prefix="/chat", tags=["Chat"])
tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)


@router.post("", summary="Send a query; JSON by default, SSE when stream=true")
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: User | None = Depends(get_current_user_optional),
) -> Any:
    query = body.query.strip()
    conversation_id = body.conversation_id or str(generate_uuid())
    version = resolve_model_version(body.model)

    with tracer.start_as_current_span("chat_endpoint") as span:
        span.set_attribute("conversation_id", conversation_id)
        span.set_attribute("stream", body.stream)
        span.set_attribute("chat_version", version)
        if not query:
            span.set_status(StatusCode.ERROR, "Missing query")
            raise HTTPException(status_code=400, detail="Missing query")

        try:
            plan = await prepare_turn(
                query=query, conversation_id=conversation_id, user=user,
                is_continuation=bool(body.conversation_id), requested_version=version,
            )
        except ConversationNotFound:
            span.set_status(StatusCode.ERROR, "Conversation not found")
            raise HTTPException(status_code=404, detail="Conversation not found")

        if plan.cached is not None:
            span.set_attribute("cache_hit", True)

        if body.stream:
            async def sse():
                async for event in run_turn(plan, background_tasks=background_tasks):
                    if event.name == "error":
                        span.set_status(StatusCode.ERROR, event.data.get("message"))
                    yield _sse_event(event.name, event.data)

            return StreamingResponse(
                sse(), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        result = await collect_turn(plan, background_tasks=background_tasks)
        if result.error is not None:
            span.set_status(StatusCode.ERROR, result.error.get("message"))
            return JSONResponse(content={
                "success": False,
                "error": result.error.get("message"),
                "conversation_id": conversation_id,
                "responseTime": result.total_ms,
            })

        return {
            "success": True,
            "data": {
                "message_id": result.message_id,
                "cached": result.cached,
                "agentSteps": result.agent_steps,
                **result.answer_data,
            },
            "conversation_id": conversation_id,
            "responseTime": result.total_ms,
        }


def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

(The WebSocket handler is added in Task 5; leave a placeholder comment `# ─── WebSocket mode (Task 5) ───` at the end.)

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd backend && rtk pytest tests/routers/test_chat_unified.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Rewrite the stream/cache tests to call the merged handler**

In each of `test_chat_stream_message_id.py`, `test_chat_stream_agent_steps.py`, `test_chat_stream_upstream.py`, `test_chat_stream_v5_fields.py`: replace calls of the form
`chat_router.chat_stream(ChatRequest(query="q"), MagicMock(), BackgroundTasks(), None)`
with
`chat_router.chat(ChatRequest(query="q", stream=True), BackgroundTasks(), None)`
(drop the `Request` positional arg; add `stream=True`). Pipeline/`_persist` assertions are unchanged. Rewrite `test_chat_cache.py` to assert the unified JSON path: a cache hit returns `result["data"]["cached"] is True`. Delete `test_chat_external_client.py`.

Run: `cd backend && rtk pytest tests/routers/test_chat_stream_message_id.py tests/routers/test_chat_stream_agent_steps.py tests/routers/test_chat_stream_upstream.py tests/routers/test_chat_stream_v5_fields.py tests/routers/test_chat_cache.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/routers/chat.py backend/tests/routers/test_chat_unified.py \
  backend/tests/routers/test_chat_stream_message_id.py backend/tests/routers/test_chat_stream_agent_steps.py \
  backend/tests/routers/test_chat_stream_upstream.py backend/tests/routers/test_chat_stream_v5_fields.py \
  backend/tests/routers/test_chat_cache.py
rtk git rm backend/tests/routers/test_chat_external_client.py
rtk git commit -m "feat: merge chat routes into one POST /chat (JSON+SSE), all versions"
```

---

## Task 5: `WS /chat` WebSocket transport

**Files:**
- Create: `backend/app/services/chat/ws.py`
- Modify: `backend/app/config.py:82` (add settings), `backend/app/routers/chat.py` (add WS handler)
- Test: `backend/tests/routers/test_chat_ws.py`

**Interfaces:**
- Consumes: `_resolve_token` from `app.auth.dependencies`; `resolve_model_version` (Task 1); `prepare_turn`/`run_turn`/`ConversationNotFound` from `app.services.chat.stream`; `settings` from `app.config`.
- Produces (in `ws.py`):
  - `Send = Callable[[dict], Awaitable[None]]`
  - `class ConnectionRegistry` with `acquire() -> bool`, `release() -> None` (reads `settings.CHAT_WS_MAX_CONNECTIONS` live).
  - `async bearer_user(websocket) -> User | None`
  - `async handle_chat_frame(raw: str | None, user: User | None, send: Send) -> None` — one query frame → event frames.
- Produces (in `chat.py`): `_connections = ConnectionRegistry()`, `chat_ws(websocket)` at `@router.websocket("")`.

- [ ] **Step 1: Add config settings**

Edit `backend/app/config.py` after line 82 (next to the `RESPONSES_WS_*` settings):

```python
    CHAT_WS_MAX_CONNECTIONS: int = 1024
    CHAT_WS_MAX_DURATION_SECONDS: int = 900
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/routers/test_chat_ws.py
"""WS /chat: connection cap, bearer auth, query-frame round trip, bad frames."""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.routers import chat as chat_router
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent
from app.services.chat.ws import ConnectionRegistry, bearer_user


class _FakeSocket:
    def __init__(self, headers=None):
        self.headers = headers or {}


@pytest.fixture
def restore_cap():
    original = settings.CHAT_WS_MAX_CONNECTIONS
    yield
    settings.CHAT_WS_MAX_CONNECTIONS = original


def test_registry_admits_up_to_the_cap(restore_cap):
    settings.CHAT_WS_MAX_CONNECTIONS = 2
    reg = ConnectionRegistry()
    assert reg.acquire() is True
    assert reg.acquire() is True
    assert reg.acquire() is False


def test_registry_release_never_negative(restore_cap):
    settings.CHAT_WS_MAX_CONNECTIONS = 1
    reg = ConnectionRegistry()
    reg.release()
    assert reg.acquire() is True
    assert reg.acquire() is False


@pytest.mark.asyncio
async def test_missing_authorization_is_anonymous(db):
    assert await bearer_user(_FakeSocket()) is None


@pytest.fixture(autouse=True)
def _isolated_registry():
    original = chat_router._connections._open
    yield
    chat_router._connections._open = original


def _events():
    return [
        ChatEvent("answer", {"answer": "คำตอบ", "sections": [], "errors": []}),
        ChatEvent("done", {"session_id": "s", "total_ms": 1, "message_id": "m"}),
    ]


def _fake_run_turn(*events):
    async def gen(plan, *, background_tasks=None):
        for e in events:
            yield e
    return gen


def _app():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(chat_router.router, prefix="/api/v1")
    return app


def test_query_frame_round_trip(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch("app.services.chat.ws.run_turn", _fake_run_turn(*_events())), \
         TestClient(_app()) as client, \
         client.websocket_connect("/api/v1/chat") as ws:
        ws.send_text(json.dumps({"query": "บัตรหาย"}))
        names = []
        while names[-1:] != ["done"]:
            names.append(json.loads(ws.receive_text())["event"])
    assert names == ["answer", "done"]


def test_malformed_frame_errors_without_closing(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch("app.services.chat.ws.run_turn", _fake_run_turn(*_events())), \
         TestClient(_app()) as client, \
         client.websocket_connect("/api/v1/chat") as ws:
        ws.send_text("not json")
        first = json.loads(ws.receive_text())
        assert first["event"] == "error"
        ws.send_text(json.dumps({"query": "บัตรหาย"}))
        names = []
        while names[-1:] != ["done"]:
            names.append(json.loads(ws.receive_text())["event"])
    assert names[-1] == "done"


def test_connection_cap_refuses_next(restore_cap, db):
    settings.CHAT_WS_MAX_CONNECTIONS = 1
    with TestClient(_app()) as client:
        with client.websocket_connect("/api/v1/chat"):
            with pytest.raises(Exception):
                with client.websocket_connect("/api/v1/chat"):
                    pass
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && rtk pytest tests/routers/test_chat_ws.py -v`
Expected: FAIL — `app.services.chat.ws` missing; no WS route.

- [ ] **Step 4: Implement `ws.py`**

```python
# backend/app/services/chat/ws.py
"""Transport-free WebSocket logic for /chat.

The router hands raw frame text in and a `send` callable out, so the whole
protocol is unit-testable without a real socket. One turn runs to completion
before the next frame is read, so exactly one response is ever in flight.
"""
import json
import logging
from typing import Awaitable, Callable

from app.auth.dependencies import _resolve_token
from app.config import settings
from app.models.user import User
from app.services.chat.model import resolve_model_version
from app.services.chat.stream import ConversationNotFound, prepare_turn, run_turn
from app.utils import generate_uuid

logger = logging.getLogger(__name__)

Send = Callable[[dict], Awaitable[None]]


class ConnectionRegistry:
    """Caps concurrent sockets; reads the setting live so tests can mutate it."""

    def __init__(self) -> None:
        self._open = 0

    def acquire(self) -> bool:
        if self._open >= settings.CHAT_WS_MAX_CONNECTIONS:
            return False
        self._open += 1
        return True

    def release(self) -> None:
        self._open = max(0, self._open - 1)


async def bearer_user(websocket) -> User | None:
    """Resolve the caller from the Authorization header; anonymous otherwise.

    Browsers cannot set headers on a WebSocket — they should use SSE. There is
    deliberately no query-parameter token fallback (it would leak into logs).
    """
    header = websocket.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        return await _resolve_token(header[7:])
    except Exception:
        return None


def _error(message: str, code: int = 400) -> dict:
    return {"event": "error", "data": {"message": message, "code": code}}


async def handle_chat_frame(raw: str | None, user: User | None, send: Send) -> None:
    if raw is None:
        await send(_error("This endpoint accepts text frames only."))
        return
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, RecursionError):
        await send(_error("Frame is not valid JSON."))
        return
    if not isinstance(payload, dict) or not str(payload.get("query", "")).strip():
        await send(_error("Frame must be a JSON object with a non-empty `query`."))
        return

    query = str(payload["query"]).strip()
    conversation_id = payload.get("conversation_id") or str(generate_uuid())
    version = resolve_model_version(payload.get("model"))
    try:
        plan = await prepare_turn(
            query=query, conversation_id=conversation_id, user=user,
            is_continuation=bool(payload.get("conversation_id")), requested_version=version,
        )
    except ConversationNotFound:
        await send(_error("Conversation not found", code=404))
        return

    async for event in run_turn(plan, background_tasks=None):
        await send({"event": event.name, "data": event.data})
```

- [ ] **Step 5: Add the WS route to `chat.py`**

Add imports at the top of `chat.py`: `import asyncio`, `import time`, `from fastapi import WebSocket, WebSocketDisconnect`, `from app.config import settings`, and `from app.services.chat.ws import ConnectionRegistry, bearer_user, handle_chat_frame`. Then append:

```python
# ─── WebSocket mode ───────────────────────────────────────────────────────────

_connections = ConnectionRegistry()


@router.websocket("")
async def chat_ws(websocket: WebSocket) -> None:
    if not _connections.acquire():
        await websocket.close(code=1013)  # try again later
        return

    async def send(frame: dict) -> None:
        await websocket.send_text(json.dumps(frame, ensure_ascii=False))

    try:
        await websocket.accept()
        user = await bearer_user(websocket)
        deadline = time.monotonic() + settings.CHAT_WS_MAX_DURATION_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await websocket.close(code=1000)
                return
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=remaining)
            except asyncio.TimeoutError:
                await websocket.close(code=1000)
                return
            websocket._raise_on_disconnect(message)
            await handle_chat_frame(message.get("text"), user, send)
    except WebSocketDisconnect:
        return
    finally:
        _connections.release()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && rtk pytest tests/routers/test_chat_ws.py -v`
Expected: PASS (6 tests).

- [ ] **Step 7: Commit**

```bash
rtk git add backend/app/services/chat/ws.py backend/app/config.py backend/app/routers/chat.py \
  backend/tests/routers/test_chat_ws.py
rtk git commit -m "feat: add WS /chat transport mirroring responses.py"
```

---

## Task 6: Prune dead helpers and obsolete tests

**Files:**
- Modify: `backend/tests/services/test_chat_turn.py` (remove `_copy_cached_answer` test + import)
- Modify: `backend/tests/test_surface_parity.py:76`

**Interfaces:** none produced; this task removes references to deleted symbols.

- [ ] **Step 1: Confirm the dead symbols are gone**

Run: `cd backend && rtk grep -rn "_copy_cached_answer\|chat_external\|chat_stream\|_parse_sse_block" app tests`
Expected: no matches in `app/routers/chat.py`; remaining matches only in tests to fix below.

- [ ] **Step 2: Remove the `_copy_cached_answer` test**

In `backend/tests/services/test_chat_turn.py`, delete the import `from app.routers.chat import _copy_cached_answer` and the test `test_copy_cached_answer_creates_two_messages_and_links_parent` (lines ~13, ~30-60). Leave the other tests intact.

- [ ] **Step 3: Fix the surface-parity expectation**

In `backend/tests/test_surface_parity.py`, remove the line `("POST", "/api/v1/chat/stream"),` (line 76) from `expected_prefixes_and_exact`.

- [ ] **Step 4: Run the affected tests**

Run: `cd backend && rtk pytest tests/services/test_chat_turn.py tests/test_surface_parity.py -v`
Expected: PASS. If `test_surface_parity` reports the WebSocket route as unexpected/missing, adjust the expected set to match the actual `_concrete_paths()` output shown in the failure (WebSocket routes are matched by path only) — do not weaken the equality assertion.

- [ ] **Step 5: Full backend suite**

Run: `cd backend && rtk pytest -q`
Expected: PASS (no references to removed routes/symbols remain).

- [ ] **Step 6: Commit**

```bash
rtk git add backend/tests/services/test_chat_turn.py backend/tests/test_surface_parity.py
rtk git commit -m "chore: drop tests bound to removed chat routes/helpers"
```

---

## Task 7: Frontend — unified `chatApi.ts` + envelope type

**Files:**
- Modify: `frontend/src/features/chat/chatApi.ts`
- Modify: `frontend/src/features/chat/chatApi.test.ts` (endpoint URL + shape)

**Interfaces:**
- Produces:
  - `interface ChatReference { number?: number; agency_id?: string; agency_name?: string; agency?: string; title?: string; url: string | null }`
  - `ChatApiResponse.data`: `{ message_id: string; cached: boolean; agentSteps: AgentStep[]; answer?: string; summary?: string; references?: ChatReference[]; sections?: unknown[]; errors?: unknown[]; debug?: unknown }`.
  - `sendChatQuery(request)` posts `{ ...request }` to `/api/v1/chat` (JSON; `stream` omitted → false).
  - `sendChatQuerySSE(request, callbacks, signal)` posts `{ ...request, stream: true }` to `/api/v1/chat` (unchanged SSE parsing).

- [ ] **Step 1: Update the frontend test first**

In `frontend/src/features/chat/chatApi.test.ts`, change the MSW handlers from `*/api/v1/chat/stream` to `*/api/v1/chat` and assert the request body carries `stream: true` for the SSE path. Add a test that `sendChatQuery` posts to `/api/v1/chat` with no `stream` flag and parses `data.answer`/`data.agentSteps`/`data.message_id` from the new envelope.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && rtk vitest run src/features/chat/chatApi.test.ts`
Expected: FAIL (URL/shape mismatch).

- [ ] **Step 3: Edit `chatApi.ts`**

- Replace `ChatApiResponse` with the passthrough shape above and add `ChatReference`.
- `sendChatQuery`: `return api.post<ChatApiResponse>('/api/v1/chat', request);` (unchanged URL; envelope type changed).
- `sendChatQuerySSE`: change `const url = ...'/api/v1/chat/stream'` → `'/api/v1/chat'`, and send `body: JSON.stringify({ ...request, stream: true })`. Keep the `Accept: text/event-stream`, idle-timeout, and SSE-parsing logic exactly as-is.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && rtk vitest run src/features/chat/chatApi.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/features/chat/chatApi.ts frontend/src/features/chat/chatApi.test.ts
rtk git commit -m "feat(fe): point chat API at unified /chat endpoint"
```

---

## Task 8: Frontend — map the new envelope in `useChat` and `agencyApi`

**Files:**
- Modify: `frontend/src/features/chat/useChat.ts:99-124`
- Modify: `frontend/src/features/agencies/agencyApi.ts:28-55`
- Test: `frontend/src/features/chat/useChat.test.tsx` (sync branch), existing agency tests

**Interfaces:**
- Consumes: `ChatApiResponse`/`ChatReference` (Task 7).
- Produces: no new exports; behavior mapping only.

- [ ] **Step 1: Update the sync-branch mapping in `useChat.ts`**

Replace the `sources` mapping (lines ~113-117) so it tolerates the v5 reference shape:

```ts
sources: (response.data.references ?? []).map((ref) => ({
  agency: ref.agency ?? ref.agency_name ?? '',
  url: ref.url ?? '',
  title: ref.title ?? ref.agency_name ?? '',
})),
```

and set `content: response.data.answer ?? response.data.summary ?? ''`. `agentSteps` usage (lines 103-112) is unchanged.

- [ ] **Step 2: Update `agencyApi.ts`**

Rewrite `queryAgency` to read the passthrough envelope (the old `data.agencies`/`data.confidence` no longer exist):

```ts
export async function queryAgency(agencyId: AgencyId, query: string): Promise<AgencyApiResponse> {
  const res = await api.post<ChatApiResponse>('/api/v1/chat', { query, model: 'onechat' });
  const answer = res.data.answer ?? res.data.summary ?? '';
  const references = (res.data.references ?? []).map((r) => ({
    title: r.title ?? r.agency_name ?? '',
    url: r.url ?? '',
  }));
  const agencyName = res.data.references?.[0]?.agency_name ?? agencyId;
  return {
    success: res.success,
    agency: agencyId,
    agencyName,
    data: { answer, references, confidence: 0 },
    responseTime: res.responseTime,
  };
}
```

Import `ChatApiResponse` from `@/features/chat/chatApi`. Keep `AgencyApiResponse` (its `confidence` field stays, defaulted to `0`).

- [ ] **Step 3: Run the frontend tests**

Run: `cd frontend && rtk vitest run src/features/chat src/features/agencies`
Expected: PASS. Update any test asserting the old `data.agencies`/`data.confidence` shape to the new envelope.

- [ ] **Step 4: Commit**

```bash
rtk git add frontend/src/features/chat/useChat.ts frontend/src/features/agencies/agencyApi.ts \
  frontend/src/features/chat/useChat.test.tsx
rtk git commit -m "feat(fe): map unified chat envelope in useChat and agencyApi"
```

---

## Task 9: Integration verification, context.md, docker

**Files:**
- Modify: `context.md`

**Interfaces:** none.

- [ ] **Step 1: Full backend + frontend suites**

Run: `cd backend && rtk pytest -q`
Run: `cd frontend && rtk vitest run`
Expected: both green.

- [ ] **Step 2: Smoke the running app (per `/run`)**

Start the stack, then confirm all three transports against `/api/v1/chat`:
- `curl -s -X POST .../api/v1/chat -d '{"query":"บัตรหาย"}'` → JSON envelope with `data.answer`.
- `curl -sN -X POST .../api/v1/chat -d '{"query":"บัตรหาย","stream":true}'` → SSE with `event: done`.
- `curl -sN -X POST .../api/v1/chat -d '{"query":"บัตรหาย","model":"onechat-v2"}'` → JSON with `data.agencies` (v2 shape, no `answer`).
- A WebSocket client to `/api/v1/chat` sending `{"query":"บัตรหาย"}` → `{"event":"answer"}` … `{"event":"done"}`.

- [ ] **Step 3: Update `context.md`**

Record: the three chat routes are now one `/chat` path (POST JSON/SSE + WS); `/chat/external` and `/chat/stream` removed; `model` selects OneChat v1–v5 (`onechat-vN`, default v5); new modules `services/chat/model.py`, `aggregate.py`, `ws.py`; new settings `CHAT_WS_MAX_CONNECTIONS`/`CHAT_WS_MAX_DURATION_SECONDS`; frontend migrated.

- [ ] **Step 4: Commit**

```bash
rtk git add context.md
rtk git commit -m "docs: update context.md for unified chat endpoint"
```

---

## Self-Review

**Spec coverage:**
- One path + 3 transports → Tasks 4 (POST JSON/SSE) + 5 (WS). ✓
- All OneChat versions via `model` → Tasks 1 (resolver) + 3 (schema) + threaded in 4/5. ✓
- Version-faithful passthrough envelope → Task 2 + Task 4 handler. ✓
- Hard cutover (delete `/chat/external`, `/chat/stream`) → Task 4. ✓
- WS mirrors responses.py (cap, header auth, deadline, one-in-flight) → Task 5. ✓
- Frontend (chatApi, useChat, agencyApi) → Tasks 7–8. ✓
- TDD test list + obsolete-test cleanup → Tasks 4–8. ✓
- context.md + commits → Task 9 (project rule). ✓

**Placeholder scan:** No TBD/TODO; every code step has real code. The only judgment call is the surface-parity WebSocket-route adjustment (Task 6 Step 4), which gives a concrete rule to follow against actual output.

**Type consistency:** `resolve_model_version(model: str | None) -> str`, `TurnResult`/`collect_turn`, `ConnectionRegistry`/`bearer_user`/`handle_chat_frame`, and `ChatApiResponse`/`ChatReference` names are used identically across producing and consuming tasks.
