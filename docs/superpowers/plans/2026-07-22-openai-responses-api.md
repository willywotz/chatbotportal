# OpenAI Responses API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the portal as an OpenAI-compatible model provider at `/api/v1/responses` over three transports — HTTP non-streaming, HTTP SSE, and WebSocket — all backed by the existing OneChat v5 pipeline.

**Architecture:** The turn pipeline currently inlined in `routers/chat.py::chat_stream` is extracted into `app/services/chat/stream.py` as a `prepare_turn()` / `run_turn()` pair. `/chat/stream` and `/responses` both become thin translators over it. OpenAI wire-format translation lives in a pure, transport-free module so all three transports share one tested implementation.

**Tech Stack:** Python 3.12, FastAPI, Tortoise ORM, httpx, pytest (`asyncio_mode=auto`), pydantic v2.

**Source spec:** `docs/superpowers/specs/2026-07-22-openai-responses-api-design.md`

## Global Constraints

- **TDD is mandatory.** Failing test → confirm it fails → minimal code → confirm it passes → commit. No exceptions.
- Prefix every shell command with `rtk` (token-optimizing proxy).
- Run tests from `backend/`: `cd backend && .venv/bin/pytest`.
- Google Python style. Comments only where they convey non-obvious information.
- American English. Avoid plural names like `xxxList`.
- **No database migration is required by this plan.** No model fields are added or changed.
- New settings must be registered in `SETTINGS_GROUPS` in `app/config.py` or `tests/test_settings_groups.py` will fail.
- The error envelope for `/responses` is OpenAI's shape, **not** `app/errors.py`'s. Every other route keeps the existing envelope.
- Never break `POST /chat`, `POST /chat/stream`, or the SPA. Task 1's existing-test suite is the gate.

## Two refinements to the spec, made during planning

Both are recorded here because the implementer will notice the difference:

1. **The spec describes one `run_chat_turn()` generator. It is split in two:** `prepare_turn()` (async function) and `run_turn()` (async generator). A generator body does not execute until its first `__anext__`, which is *after* `StreamingResponse` has already committed a 200 to the client — so a 404 for an unknown conversation could never be returned. `prepare_turn()` does everything that must be able to fail loudly (conversation lookup, cache probe, session warm-up); `run_turn()` streams and persists.
2. **The assistant message id is pre-allocated.** OpenAI requires the response `id` in the first streamed event (`response.created`), but our id historically came from the DB insert at the *end* of the turn. `Message.id` is a `UUIDField` with an app-side default, so an explicit id can be passed in. `save_turn()` gains an optional `assistant_message_id` parameter, `TurnPlan` carries it, and `resp_<id>` is stable from the first event to the last.

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `backend/app/services/chat/stream.py` | Transport-free turn pipeline: `prepare_turn`, `run_turn`, `ChatEvent`, `TurnPlan` |
| `backend/app/services/responses/__init__.py` | Package marker |
| `backend/app/services/responses/errors.py` | `ResponsesApiError` + OpenAI error envelope |
| `backend/app/services/responses/request.py` | Model-id resolution and `input` → query extraction (pure) |
| `backend/app/services/responses/continuity.py` | `previous_response_id` / `conversation` → `conversation_id` |
| `backend/app/services/responses/translate.py` | `ResponseAccumulator`: `ChatEvent` → OpenAI events + final `Response` (pure) |
| `backend/app/services/responses/session.py` | `WsSession.handle_text()` — WebSocket frame logic, socket-free |
| `backend/app/schemas/responses.py` | `ResponsesRequest` pydantic model |
| `backend/app/routers/responses.py` | HTTP POST + WebSocket routes; thin |
| `spec/openai-responses.md` | The wire contract we implement |

**Modified:** `backend/app/routers/chat.py`, `backend/app/services/chat/turn.py`, `backend/app/auth/dependencies.py`, `backend/app/config.py`, `backend/app/errors.py`, `backend/app/main.py`, `default.conf`, `docs/quickstart.md`, `CONTEXT.md`.

**Tests created:** `backend/tests/services/test_chat_turn_stream.py`, `backend/tests/services/test_responses_request.py`, `backend/tests/services/test_responses_continuity.py`, `backend/tests/services/test_responses_translate.py`, `backend/tests/services/test_responses_ws_session.py`, `backend/tests/routers/test_responses_http.py`, `backend/tests/routers/test_responses_auth.py`.

---

### Task 1: Extract the turn pipeline into `services/chat/stream.py`

The riskiest task: it moves the hottest path in the product. It is behaviour-preserving by construction, and the existing `/chat/stream` tests are the gate.

**Files:**
- Create: `backend/app/services/chat/stream.py`
- Modify: `backend/app/services/chat/turn.py` (add `assistant_message_id` param)
- Modify: `backend/app/routers/chat.py:181-341` (replace `_stream_upstream`, `chat_stream`, `_save_stream_conversation`)
- Test: `backend/tests/services/test_chat_turn_stream.py`

**Interfaces:**
- Produces:
  - `ChatEvent(NamedTuple)` with fields `name: str`, `data: dict`
  - `ConversationNotFound(Exception)`
  - `TurnPlan` dataclass: `query: str`, `conversation_id: str`, `user: User | None`, `stream_version: str`, `upstream_url: str`, `assistant_message_id: uuid.UUID`, `cached: tuple | None`
  - `async prepare_turn(*, query: str, conversation_id: str, user, is_continuation: bool) -> TurnPlan`
  - `async run_turn(plan: TurnPlan, *, background_tasks: BackgroundTasks | None = None) -> AsyncIterator[ChatEvent]`
  - `_stream_upstream() -> tuple[str, str]` (moved here, re-exported from `routers/chat.py`)
  - `save_turn(..., assistant_message_id: uuid.UUID | None = None)`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_chat_turn_stream.py`:

```python
"""The turn pipeline is transport-free: prepare_turn/run_turn own the whole
turn, and /chat/stream is only an SSE formatter over it."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks

from app.models.conversation import Conversation, Message
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ConversationNotFound, prepare_turn, run_turn


@pytest.mark.asyncio
async def test_prepare_turn_allocates_assistant_message_id(db):
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)):
        plan = await prepare_turn(
            query="q", conversation_id=str(uuid.uuid4()), user=None, is_continuation=False
        )
    assert isinstance(plan.assistant_message_id, uuid.UUID)
    assert plan.cached is None
    assert plan.stream_version == "v5"


@pytest.mark.asyncio
async def test_prepare_turn_raises_for_unknown_conversation(db):
    with pytest.raises(ConversationNotFound):
        await prepare_turn(
            query="q", conversation_id=str(uuid.uuid4()), user=None, is_continuation=True
        )


@pytest.mark.asyncio
async def test_run_turn_persists_with_the_preallocated_id(db):
    conv_id = str(uuid.uuid4())
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)):
        plan = await prepare_turn(
            query="q", conversation_id=conv_id, user=None, is_continuation=False
        )

    async def fake_stream(plan_arg, background_tasks):
        yield turn_stream.ChatEvent("step", {"name": "summarize"})
        yield turn_stream.ChatEvent("answer", {"answer": "คำตอบ", "sections": [], "errors": []})
        yield turn_stream.ChatEvent("done", {"session_id": conv_id, "total_ms": 12})

    with patch.object(turn_stream, "_stream_live", new=fake_stream):
        names = [ev.name async for ev in run_turn(plan, background_tasks=BackgroundTasks())]

    assert names == ["step", "answer", "done"]


@pytest.mark.asyncio
async def test_run_turn_replays_a_cache_hit(db):
    conv = await Conversation.create(status="success")
    user_msg = await Message.create(conversation=conv, role="user", content="q")
    asst_msg = await Message.create(
        parent_id=user_msg.id, conversation=conv, role="assistant", content="cached answer"
    )
    conn_log = MagicMock(response_body=json.dumps({"answer": "cached answer"}))

    with patch.object(
        turn_stream, "find_similar_question",
        new=AsyncMock(return_value=(user_msg, asst_msg, conn_log)),
    ):
        plan = await prepare_turn(
            query="q", conversation_id=str(uuid.uuid4()), user=None, is_continuation=False
        )
    assert plan.cached is not None

    events = [ev async for ev in run_turn(plan, background_tasks=BackgroundTasks())]
    assert [e.name for e in events] == ["answer", "done"]
    assert events[0].data["answer"] == "cached answer"
    assert events[1].data["message_id"] == str(plan.assistant_message_id)


@pytest.mark.asyncio
async def test_save_turn_honours_an_explicit_assistant_message_id(db):
    from app.services.chat.turn import save_turn

    wanted = uuid.uuid4()
    saved = await save_turn(
        query="q", conversation_id=str(uuid.uuid4()), answer="a", references=[],
        category=None, agency_ids=[], response_time=0, user=None, succeeded=True,
        assistant_message_id=wanted,
    )
    assert saved.assistant_message_id == str(wanted)
    assert (await Message.get(id=wanted)).content == "a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/services/test_chat_turn_stream.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.chat.stream'`

- [ ] **Step 3: Add `assistant_message_id` to `save_turn`**

In `backend/app/services/chat/turn.py`, add the parameter to the signature (after `title`):

```python
    title: str | None = None,
    assistant_message_id: uuid.UUID | None = None,
) -> SavedTurn:
```

Add `import uuid` at the top of the file. Then in the `Message.create` call for the assistant message, pass the id through — Tortoise accepts an explicit primary key, and `None` falls back to the field's `generate_uuid` default:

```python
        asst_msg = await Message.create(
            id=assistant_message_id or generate_uuid(),
            parent_id=user_msg.id,
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            sources=references,
            response_time=response_time,
            agency_ids=agency_ids,
            errors=errors or [],
            summary=summary,
            summary_references=summary_references or [],
        )
```

Add `generate_uuid` to the existing import: `from app.utils import generate_uuid, now`.

Extend the docstring with one line:

```
    `assistant_message_id` pre-allocates the assistant row's primary key so a
    streaming transport can name the response before the turn is persisted.
```

- [ ] **Step 4: Create `app/services/chat/stream.py`**

```python
"""Transport-free chat-turn pipeline, shared by /chat/stream and /responses.

Split in two on purpose. `prepare_turn()` does everything that must be able to
fail before any bytes are committed to the client — conversation lookup,
similarity-cache probe, session warm-up — so a transport can still return a
plain HTTP error. `run_turn()` is the generator: it streams the upstream,
persists the turn, and yields the terminal `done` event carrying the real
message id.
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, NamedTuple

import httpx
from fastapi import BackgroundTasks
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from tortoise.exceptions import DoesNotExist

from app.config import settings
from app.models.connection_log import ConnectionLog
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.chat.llm import classify_message_category
from app.services.chat.turn import save_turn
from app.services.log_sanitize import sanitize_body
from app.services.session import ensure_session_warmed
from app.services.similarity import find_similar_question
from app.utils import generate_uuid

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Tasks scheduled without a FastAPI BackgroundTasks (the WebSocket path) must be
# strongly referenced or the loop may collect them mid-flight.
_background_tasks: set[asyncio.Task] = set()


class ChatEvent(NamedTuple):
    """One OneChat pipeline event: the upstream vocabulary, unchanged."""

    name: str
    data: dict


class ConversationNotFound(Exception):
    """A continuation named a conversation that does not exist."""


@dataclass
class TurnPlan:
    query: str
    conversation_id: str
    user: User | None
    stream_version: str
    upstream_url: str
    assistant_message_id: uuid.UUID
    cached: tuple[Message, Message, Any] | None = None


def _stream_upstream() -> tuple[str, str]:
    """Resolve (version, url) for the streaming upstream from CHAT_STREAM_VERSION.

    Unknown values fall back to v5 rather than calling a URL that does not exist,
    so a typo in the /settings override degrades to the default instead of
    breaking chat outright.
    """
    version = (settings.CHAT_STREAM_VERSION or "").strip().lower()
    if version == "v4":
        return "v4", settings.ONECHAT_V4_URL
    if version != "v5":
        logger.warning("Unknown CHAT_STREAM_VERSION %r — falling back to v5", settings.CHAT_STREAM_VERSION)
    return "v5", settings.ONECHAT_V5_URL


async def prepare_turn(
    *, query: str, conversation_id: str, user: User | None, is_continuation: bool
) -> TurnPlan:
    """Resolve everything needed to run a turn, failing loudly if it cannot.

    Raises ConversationNotFound when `is_continuation` names an unknown id.
    """
    stream_version, upstream_url = _stream_upstream()
    plan = TurnPlan(
        query=query,
        conversation_id=conversation_id,
        user=user,
        stream_version=stream_version,
        upstream_url=upstream_url,
        assistant_message_id=generate_uuid(),
    )

    if not is_continuation:
        plan.cached = await find_similar_question(query=query)
        return plan

    try:
        conv = await Conversation.get(id=conversation_id)
    except DoesNotExist:
        raise ConversationNotFound(conversation_id)
    try:
        await ensure_session_warmed(conv, settings.ONECHAT_V3_URL, settings.MCP_ENDPOINT_URL)
    except Exception:
        logger.warning("Session warm-up failed for conversation %s", conversation_id)
    return plan


async def run_turn(
    plan: TurnPlan, *, background_tasks: BackgroundTasks | None = None
) -> AsyncIterator[ChatEvent]:
    """Stream one turn to completion, persisting it before the terminal `done`."""
    if plan.cached is not None:
        async for event in _replay_cached(plan, background_tasks):
            yield event
        return
    async for event in _stream_live(plan, background_tasks):
        yield event


async def _replay_cached(
    plan: TurnPlan, background_tasks: BackgroundTasks | None
) -> AsyncIterator[ChatEvent]:
    user_msg, asst_msg, conn_log = plan.cached
    await asyncio.sleep(0.01)
    try:
        answer_data = json.loads(conn_log.response_body)
    except Exception:
        answer_data = {"answer": asst_msg.content}

    assistant_id = await _persist(
        plan, answer_data=answer_data, session_id=None,
        total_ms=0, latency_ms=0, thread_name=None, background_tasks=background_tasks,
    )
    yield ChatEvent("answer", {
        "answer": asst_msg.content,
        "summary": answer_data.get("summary") or asst_msg.summary or "",
        "references": answer_data.get("references") or asst_msg.summary_references or [],
    })
    yield ChatEvent("done", {
        "session_id": plan.conversation_id, "total_ms": 0, "message_id": str(assistant_id),
    })


async def _stream_live(
    plan: TurnPlan, background_tasks: BackgroundTasks | None
) -> AsyncIterator[ChatEvent]:
    payload = {
        "query": plan.query,
        "mcp_endpoint_url": settings.MCP_ENDPOINT_URL,
        "session_id": plan.conversation_id,
    }
    answer_data = None
    session_id = None
    total_ms = None
    done_event_data = None
    thread_name = None
    start_ns = time.perf_counter_ns()
    log_latency_ms = 0
    version = plan.stream_version

    try:
        async with httpx.AsyncClient(timeout=settings.V4_STREAM_TIMEOUT) as client:
            async with client.stream(
                "POST", plan.upstream_url,
                headers={"Content-Type": "application/json"}, json=payload,
            ) as resp:
                if resp.status_code != 200:
                    error_msg = f"OneChat {version} returned {resp.status_code}"
                    try:
                        error_body = await resp.aread()
                        error_msg = f"{error_msg}: {error_body.decode()[:200]}"
                    except Exception:
                        pass
                    yield ChatEvent("error", {"message": error_msg, "code": resp.status_code})
                    yield ChatEvent("done", {"session_id": plan.conversation_id, "total_ms": 0})
                    return

                log_latency_ms = int((time.perf_counter_ns() - start_ns) // 1_000_000)
                buffer = ""
                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_block, buffer = buffer.split("\n\n", 1)
                        parsed = _parse_sse_block(event_block)
                        if not parsed:
                            continue
                        event_name, event_data = parsed
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

    except httpx.ReadTimeout:
        yield ChatEvent("error", {"message": f"OneChat {version} connection timed out", "code": 504})
        yield ChatEvent("done", {"session_id": plan.conversation_id, "total_ms": 0})
        return
    except Exception as e:
        yield ChatEvent("error", {"message": str(e), "code": 500})
        yield ChatEvent("done", {"session_id": plan.conversation_id, "total_ms": 0})
        return

    if answer_data:
        assistant_id = await _persist(
            plan, answer_data=answer_data, session_id=session_id, total_ms=total_ms,
            latency_ms=log_latency_ms, thread_name=thread_name, background_tasks=background_tasks,
        )
        yield ChatEvent("done", {
            **(done_event_data or {}),
            "session_id": plan.conversation_id,
            "message_id": str(assistant_id),
        })
    elif done_event_data is not None:
        yield ChatEvent("done", {**done_event_data, "session_id": plan.conversation_id})


def _parse_sse_block(block: str) -> tuple[str, Any] | None:
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


def _schedule_classification(message_id: str, query: str, answer: str,
                             background_tasks: BackgroundTasks | None) -> None:
    """Schedule category classification on whichever mechanism is available.

    WebSocket routes have no FastAPI BackgroundTasks — there is no response for
    the framework to hang them off — so they fall back to a tracked asyncio task.
    """
    if background_tasks is not None:
        background_tasks.add_task(classify_message_category, message_id, query, answer)
        return
    task = asyncio.create_task(classify_message_category(message_id, query, answer))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _persist(
    plan: TurnPlan, *, answer_data: dict, session_id: str | None, total_ms: int | None,
    latency_ms: int, thread_name: str | None, background_tasks: BackgroundTasks | None,
) -> Any:
    """Save the turn via save_turn and write its ConnectionLog."""
    answer = answer_data.get("answer", "").strip()
    errors = answer_data.get("errors", [])
    sections = answer_data.get("sections", [])
    summary = (answer_data.get("summary") or "").strip() or None
    # v5 `references[]` are scoped to `summary`; `sources` keeps its legacy
    # section-derived meaning and stays empty on the stream path.
    summary_references = answer_data.get("references") or []

    agency_ids = []
    for sec in sections:
        if "agencies" in sec:
            agency_ids.extend([ag["id"] for ag in sec["agencies"]])

    response_time = total_ms if total_ms else latency_ms

    saved = await save_turn(
        query=plan.query, conversation_id=plan.conversation_id, answer=answer,
        references=[], category=None, agency_ids=agency_ids,
        response_time=response_time, user=plan.user, succeeded=bool(answer),
        external_session_id=session_id, errors=errors, summary=summary,
        summary_references=summary_references, title=thread_name,
        assistant_message_id=plan.assistant_message_id,
    )
    await ConnectionLog.create(
        id=str(generate_uuid()),
        action="query",
        connection_type=f"external_chat_{plan.stream_version}",
        status="success" if answer else "error",
        latency_ms=latency_ms,
        detail=sanitize_body(f"{plan.stream_version} stream query: {plan.query[:100]}"),
        request_body=sanitize_body(
            json.dumps({"query": plan.query, "session_id": plan.conversation_id})
        ),
        response_body=sanitize_body(json.dumps(answer_data, ensure_ascii=False)),
        message_id=saved.user_message_id,
        assistant_message_id=saved.assistant_message_id,
    )
    _schedule_classification(saved.user_message_id, plan.query, answer, background_tasks)
    return saved.assistant_message_id
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/services/test_chat_turn_stream.py -v`
Expected: PASS — 5 passed

- [ ] **Step 6: Rewrite `chat_stream` as an SSE formatter**

In `backend/app/routers/chat.py`, delete `_stream_upstream` (lines 181-193), `_save_stream_conversation` (lines 422-473), and the body of `chat_stream` (lines 198-341). Replace the chat_stream block with:

```python
# ─── Stream endpoint (OneChat v5 SSE) ─────────────────────────────────────────

@router.post("/stream", summary="Send a query and receive SSE streaming response")
async def chat_stream(body: ChatRequest, request: Request, background_tasks: BackgroundTasks, user: User | None = Depends(get_current_user_optional)):
    """Format the shared turn pipeline as SSE. All logic lives in services/chat/stream.py."""
    if user is not None:
        await enforce_user_rate_limit(user)
    try:
        await check_global_budget()
        if user is not None:
            await check_user_quota(user.id)
    except QuotaExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))

    query = body.query.strip()
    conversation_id = body.conversation_id or str(generate_uuid())

    with tracer.start_as_current_span("chat_stream_endpoint") as span:
        span.set_attribute("conversation_id", conversation_id)
        if not query:
            span.set_status(StatusCode.ERROR, "Missing query")
            raise HTTPException(status_code=400, detail="Missing query")
        span.set_attribute("query", query)

        try:
            plan = await prepare_turn(
                query=query, conversation_id=conversation_id, user=user,
                is_continuation=bool(body.conversation_id),
            )
        except ConversationNotFound:
            span.set_status(StatusCode.ERROR, "Conversation not found for session warm-up")
            raise HTTPException(status_code=404, detail="Conversation not found")

        span.set_attribute("chat_stream_version", plan.stream_version)
        if plan.cached is not None:
            span.set_attribute("cache_hit", True)

        async def sse():
            async for event in run_turn(plan, background_tasks=background_tasks):
                yield _sse_event(event.name, event.data)

        return StreamingResponse(
            sse(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
```

Update the imports at the top of `chat.py`. Remove now-unused ones (`asyncio`, `time`, `httpx`, `ConnectionLog`, `sanitize_body`, `save_turn`, `find_similar_question`, `ensure_session_warmed` are still needed by `chat_external`, so remove only what the linter flags) and add:

```python
from app.services.chat.stream import (
    ConversationNotFound,
    _stream_upstream,  # re-exported: tests/routers/test_chat_stream_version.py imports it from here
    prepare_turn,
    run_turn,
)
```

Keep `_sse_event`, `_parse_sse_block` and `_copy_cached_answer` in `chat.py` — `chat_external` (v3 sync) still uses the last one, and `_sse_event` is now the router's only formatting concern.

- [ ] **Step 7: Run the whole backend suite to prove nothing regressed**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS — the pre-existing `tests/routers/test_chat_stream_message_id.py`, `test_chat_stream_v5_fields.py`, `test_chat_stream_version.py`, `test_chat_cache.py` and `tests/services/test_chat_turn.py` all still pass.

If `test_chat_stream_v5_fields.py` or `test_chat_turn.py` fail on `ImportError: cannot import name '_save_stream_conversation'`, that is expected — they import a function that no longer exists. Update those imports to use `app.services.chat.stream._persist`, adapting the call sites to pass a `TurnPlan` instead of loose kwargs:

```python
from app.services.chat.stream import TurnPlan, _persist
from app.utils import generate_uuid


def _plan(conv_id: str, query: str = "q") -> TurnPlan:
    return TurnPlan(
        query=query, conversation_id=conv_id, user=None, stream_version="v5",
        upstream_url="http://upstream/v5/chat", assistant_message_id=generate_uuid(),
    )
```

Then each `await _save_stream_conversation(query=..., conversation_id=cid, answer_data=D, session_id=S, total_ms=T, latency_ms=L, user=None, background_tasks=BackgroundTasks())` becomes `await _persist(_plan(cid), answer_data=D, session_id=S, total_ms=T, latency_ms=L, thread_name=None, background_tasks=BackgroundTasks())`. Do not change what any test *asserts* — only how it calls in.

- [ ] **Step 8: Commit**

```bash
rtk git add backend/app/services/chat/stream.py backend/app/services/chat/turn.py backend/app/routers/chat.py backend/tests/
rtk git commit -m "refactor(chat): extract the turn pipeline into services/chat/stream

prepare_turn/run_turn are transport-free so /chat/stream and the coming
/responses endpoint share one implementation. Behaviour-preserving; the
existing stream suite is the gate."
```

---

### Task 2: OpenAI error envelope

**Files:**
- Create: `backend/app/services/responses/__init__.py` (empty)
- Create: `backend/app/services/responses/errors.py`
- Modify: `backend/app/errors.py`
- Test: `backend/tests/services/test_responses_translate.py` (first tests land here)

**Interfaces:**
- Produces: `ResponsesApiError(message, *, type="invalid_request_error", param=None, code=None, status=400)` with `.envelope() -> dict`; `register_responses_error_handler(app)`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_responses_translate.py`:

```python
"""The /responses surface speaks OpenAI's error envelope, not the portal's."""

import pytest

from app.services.responses.errors import ResponsesApiError


def test_envelope_matches_openai_shape():
    err = ResponsesApiError("Unknown model 'gpt-5'.", param="model")
    assert err.status == 400
    assert err.envelope() == {
        "error": {
            "message": "Unknown model 'gpt-5'.",
            "type": "invalid_request_error",
            "param": "model",
            "code": None,
        }
    }


def test_not_found_carries_its_code_and_status():
    err = ResponsesApiError(
        "Previous response with id 'resp_abc' not found",
        code="previous_response_not_found", status=404,
    )
    assert err.status == 404
    assert err.envelope()["error"]["code"] == "previous_response_not_found"
    assert err.envelope()["error"]["param"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_translate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.responses'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/responses/__init__.py` as an empty file.

Create `backend/app/services/responses/errors.py`:

```python
"""OpenAI-shaped errors, scoped to the /responses surface.

Every other route uses app/errors.py's {"error": {"code", "message", ...}}
envelope. An OpenAI SDK client parses {"error": {"message", "type", "param",
"code"}} instead, so this router deliberately diverges.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ResponsesApiError(Exception):
    def __init__(
        self, message: str, *, type: str = "invalid_request_error",
        param: str | None = None, code: str | None = None, status: int = 400,
    ):
        super().__init__(message)
        self.message = message
        self.type = type
        self.param = param
        self.code = code
        self.status = status

    def envelope(self) -> dict:
        return {
            "error": {
                "message": self.message,
                "type": self.type,
                "param": self.param,
                "code": self.code,
            }
        }


def register_responses_error_handler(app: FastAPI) -> None:
    @app.exception_handler(ResponsesApiError)
    async def _responses_error(_req: Request, exc: ResponsesApiError):
        return JSONResponse(status_code=exc.status, content=exc.envelope())
```

In `backend/app/errors.py`, call it from `register_error_handlers` so the app wires one place. Add at the end of that function:

```python
    from app.services.responses.errors import register_responses_error_handler

    register_responses_error_handler(app)
```

The import is function-local to keep `app/errors.py` free of a service-layer import at module load.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_translate.py -v`
Expected: PASS — 2 passed

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/responses/ backend/app/errors.py backend/tests/services/test_responses_translate.py
rtk git commit -m "feat(responses): add the OpenAI-shaped error envelope"
```

---

### Task 3: Request parsing — model resolution and `input` extraction

**Files:**
- Create: `backend/app/schemas/responses.py`
- Create: `backend/app/services/responses/request.py`
- Test: `backend/tests/services/test_responses_request.py`

**Interfaces:**
- Consumes: `ResponsesApiError` (Task 2); `_stream_upstream` (Task 1).
- Produces:
  - `ResponsesRequest` pydantic model with fields `model: str`, `input: str | list`, `previous_response_id: str | None`, `conversation: str | None`, `stream: bool`, `store: bool`, `generate: bool`
  - `resolve_model(model: str) -> tuple[str, str]` returning `(canonical_model_id, stream_version)`
  - `extract_query(value: str | list) -> str`
  - `MODEL_IDS: dict[str, str | None]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_responses_request.py`:

```python
"""Mapping an OpenAI request onto a portal turn."""

import pytest

from app.config import settings
from app.schemas.responses import ResponsesRequest
from app.services.responses.errors import ResponsesApiError
from app.services.responses.request import extract_query, resolve_model


@pytest.fixture
def restore_version():
    original = settings.CHAT_STREAM_VERSION
    yield
    settings.CHAT_STREAM_VERSION = original


def test_bare_model_follows_the_configured_version(restore_version):
    settings.CHAT_STREAM_VERSION = "v4"
    assert resolve_model("thai-citizen-guide") == ("thai-citizen-guide", "v4")


def test_suffixed_models_pin_the_upstream(restore_version):
    settings.CHAT_STREAM_VERSION = "v4"
    assert resolve_model("thai-citizen-guide-v5") == ("thai-citizen-guide-v5", "v5")
    assert resolve_model("thai-citizen-guide-v4") == ("thai-citizen-guide-v4", "v4")


def test_unknown_model_is_a_400_on_the_model_param():
    with pytest.raises(ResponsesApiError) as exc:
        resolve_model("gpt-5")
    assert exc.value.status == 400
    assert exc.value.param == "model"
    assert "gpt-5" in exc.value.message


def test_string_input_is_the_query():
    assert extract_query("บัตรประชาชนหาย") == "บัตรประชาชนหาย"


def test_array_input_uses_the_last_user_message():
    value = [
        {"role": "user", "content": [{"type": "input_text", "text": "first"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "answer"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "second"}]},
    ]
    assert extract_query(value) == "second"


def test_array_input_joins_multiple_text_parts():
    value = [{"role": "user", "content": [
        {"type": "input_text", "text": "part one"},
        {"type": "input_text", "text": "part two"},
    ]}]
    assert extract_query(value) == "part one part two"


def test_array_input_accepts_a_plain_string_content():
    assert extract_query([{"role": "user", "content": "hello"}]) == "hello"


def test_array_input_rejects_a_trailing_assistant_message():
    value = [{"role": "assistant", "content": [{"type": "output_text", "text": "a"}]}]
    with pytest.raises(ResponsesApiError) as exc:
        extract_query(value)
    assert exc.value.param == "input"


def test_empty_input_is_rejected():
    for value in ("", "   ", []):
        with pytest.raises(ResponsesApiError):
            extract_query(value)


def test_unsupported_fields_are_accepted_and_ignored():
    req = ResponsesRequest.model_validate({
        "model": "thai-citizen-guide",
        "input": "hi",
        "temperature": 0.7,
        "tools": [{"type": "function", "name": "x"}],
        "max_output_tokens": 100,
    })
    assert req.input == "hi"
    assert not hasattr(req, "temperature")


def test_store_and_generate_default_true():
    req = ResponsesRequest.model_validate({"model": "thai-citizen-guide", "input": "hi"})
    assert req.store is True
    assert req.generate is True
    assert req.stream is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_request.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.responses'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/schemas/responses.py`:

```python
"""Request body for the OpenAI-compatible /responses endpoint.

`extra="ignore"` is deliberate: the OpenAI SDK sends many fields the portal
cannot honour (temperature, tools, max_output_tokens, …) and rejecting them
would break ordinary clients for no benefit.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model: str = "thai-citizen-guide"
    input: str | list[dict[str, Any]] = ""
    previous_response_id: str | None = None
    conversation: str | None = None
    stream: bool = False
    # Accepted for SDK compatibility; the portal always persists (see the design doc).
    store: bool = True
    # WebSocket warm-up: resolve and warm the session without generating.
    generate: bool = True
```

Create `backend/app/services/responses/request.py`:

```python
"""Translate an OpenAI Responses request into portal turn parameters."""
from typing import Any

from app.services.chat.stream import _stream_upstream
from app.services.responses.errors import ResponsesApiError

DEFAULT_MODEL_ID = "thai-citizen-guide"

# None → follow CHAT_STREAM_VERSION; otherwise pin that OneChat upstream.
MODEL_IDS: dict[str, str | None] = {
    DEFAULT_MODEL_ID: None,
    "thai-citizen-guide-v5": "v5",
    "thai-citizen-guide-v4": "v4",
}


def resolve_model(model: str) -> tuple[str, str]:
    """Return (canonical model id, OneChat stream version) or raise a 400."""
    if model not in MODEL_IDS:
        raise ResponsesApiError(
            f"Unknown model '{model}'. Supported models: {', '.join(sorted(MODEL_IDS))}.",
            param="model",
        )
    pinned = MODEL_IDS[model]
    if pinned is not None:
        return model, pinned
    version, _url = _stream_upstream()
    return model, version


def extract_query(value: str | list[dict[str, Any]]) -> str:
    """Reduce `input` to the single user question the pipeline takes.

    OneChat keeps conversation history server-side, so only the newest user
    message is forwarded; earlier items in a client-supplied array are context
    the upstream already has.
    """
    if isinstance(value, str):
        query = value.strip()
        if not query:
            raise ResponsesApiError("`input` must not be empty.", param="input")
        return query

    if not value:
        raise ResponsesApiError("`input` must not be empty.", param="input")

    last = value[-1]
    if last.get("role") != "user":
        raise ResponsesApiError(
            "The last item of `input` must be a message with role 'user'.", param="input",
        )

    content = last.get("content", "")
    if isinstance(content, str):
        text = content.strip()
    else:
        text = " ".join(
            part.get("text", "").strip()
            for part in content
            if isinstance(part, dict) and part.get("text")
        ).strip()

    if not text:
        raise ResponsesApiError("`input` must not be empty.", param="input")
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_request.py -v`
Expected: PASS — 11 passed

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/responses.py backend/app/services/responses/request.py backend/tests/services/test_responses_request.py
rtk git commit -m "feat(responses): map OpenAI model ids and input onto a portal turn"
```

---

### Task 4: Conversation continuity

**Files:**
- Create: `backend/app/services/responses/continuity.py`
- Test: `backend/tests/services/test_responses_continuity.py`

**Interfaces:**
- Consumes: `ResponsesApiError` (Task 2).
- Produces: `async resolve_conversation(*, previous_response_id: str | None, conversation: str | None, cache: dict[str, str] | None = None) -> tuple[str, bool]` returning `(conversation_id, is_continuation)`; `response_id_for(assistant_message_id) -> str`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_responses_continuity.py`:

```python
"""previous_response_id / conversation → the portal's conversation_id."""

import uuid

import pytest

from app.models.conversation import Conversation, Message
from app.services.responses.continuity import resolve_conversation, response_id_for
from app.services.responses.errors import ResponsesApiError


@pytest.mark.asyncio
async def test_no_continuation_starts_a_new_conversation(db):
    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id=None, conversation=None
    )
    assert is_continuation is False
    uuid.UUID(conversation_id)


@pytest.mark.asyncio
async def test_previous_response_id_resolves_to_its_conversation(db):
    conv = await Conversation.create(status="success")
    asst = await Message.create(conversation=conv, role="assistant", content="a")

    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id=response_id_for(asst.id), conversation=None
    )
    assert conversation_id == str(conv.id)
    assert is_continuation is True


@pytest.mark.asyncio
async def test_unknown_previous_response_id_is_a_404(db):
    with pytest.raises(ResponsesApiError) as exc:
        await resolve_conversation(
            previous_response_id=f"resp_{uuid.uuid4()}", conversation=None
        )
    assert exc.value.status == 404
    assert exc.value.code == "previous_response_not_found"


@pytest.mark.asyncio
async def test_malformed_previous_response_id_is_a_404(db):
    with pytest.raises(ResponsesApiError) as exc:
        await resolve_conversation(previous_response_id="resp_not-a-uuid", conversation=None)
    assert exc.value.code == "previous_response_not_found"


@pytest.mark.asyncio
async def test_connection_cache_short_circuits_the_db(db):
    known = str(uuid.uuid4())
    cache = {"resp_abc": known}
    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id="resp_abc", conversation=None, cache=cache
    )
    assert conversation_id == known
    assert is_continuation is True


@pytest.mark.asyncio
async def test_conversation_param_is_used_directly(db):
    conv = await Conversation.create(status="success")
    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id=None, conversation=str(conv.id)
    )
    assert conversation_id == str(conv.id)
    assert is_continuation is True


@pytest.mark.asyncio
async def test_conflicting_pair_is_a_400(db):
    conv = await Conversation.create(status="success")
    asst = await Message.create(conversation=conv, role="assistant", content="a")
    with pytest.raises(ResponsesApiError) as exc:
        await resolve_conversation(
            previous_response_id=response_id_for(asst.id), conversation=str(uuid.uuid4())
        )
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_agreeing_pair_is_accepted(db):
    conv = await Conversation.create(status="success")
    asst = await Message.create(conversation=conv, role="assistant", content="a")
    conversation_id, _ = await resolve_conversation(
        previous_response_id=response_id_for(asst.id), conversation=str(conv.id)
    )
    assert conversation_id == str(conv.id)


def test_response_id_is_prefixed():
    message_id = uuid.uuid4()
    assert response_id_for(message_id) == f"resp_{message_id}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_continuity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.responses.continuity'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/responses/continuity.py`:

```python
"""Conversation continuity for the OpenAI-compatible surface.

A response id is `resp_<assistant message uuid>`, so a continuation resolves by
loading that message and reading its conversation. A WebSocket may pass a
connection-local cache to skip the query for the most recent response, matching
OpenAI's connection-local semantics.
"""
import uuid

from app.models.conversation import Message
from app.services.responses.errors import ResponsesApiError
from app.utils import generate_uuid

RESPONSE_ID_PREFIX = "resp_"


def response_id_for(assistant_message_id) -> str:
    return f"{RESPONSE_ID_PREFIX}{assistant_message_id}"


def _not_found(previous_response_id: str) -> ResponsesApiError:
    return ResponsesApiError(
        f"Previous response with id '{previous_response_id}' not found",
        type="invalid_request_error",
        param="previous_response_id",
        code="previous_response_not_found",
        status=404,
    )


async def resolve_conversation(
    *,
    previous_response_id: str | None,
    conversation: str | None,
    cache: dict[str, str] | None = None,
) -> tuple[str, bool]:
    """Return (conversation_id, is_continuation)."""
    resolved: str | None = None

    if previous_response_id:
        if cache is not None and previous_response_id in cache:
            resolved = cache[previous_response_id]
        else:
            raw = previous_response_id.removeprefix(RESPONSE_ID_PREFIX)
            try:
                message_id = uuid.UUID(raw)
            except ValueError:
                raise _not_found(previous_response_id)
            message = await Message.filter(id=message_id, role="assistant").first()
            if message is None:
                raise _not_found(previous_response_id)
            resolved = str(message.conversation_id)

    if conversation:
        if resolved is not None and resolved != conversation:
            raise ResponsesApiError(
                "`conversation` does not match the conversation of "
                "`previous_response_id`; supply only one.",
                param="conversation",
            )
        resolved = conversation

    if resolved is None:
        return str(generate_uuid()), False
    return resolved, True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_continuity.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/responses/continuity.py backend/tests/services/test_responses_continuity.py
rtk git commit -m "feat(responses): resolve continuity from previous_response_id"
```

---

### Task 5: The event translator

The core of the feature and the place the tests concentrate: pure, synchronous, transport-free.

**Files:**
- Create: `backend/app/services/responses/translate.py`
- Test: `backend/tests/services/test_responses_translate.py` (append to Task 2's file)

**Interfaces:**
- Consumes: `ChatEvent` (Task 1); `response_id_for` (Task 4).
- Produces: `ResponseAccumulator(response_id, model, conversation_id, *, cached=False, stream_version="v5")` with methods `created_event() -> dict`, `consume(event: ChatEvent) -> list[dict]`, `final_response() -> dict`, `failed_event(message: str, code: int | None = None) -> dict`, and attribute `answer: str`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_responses_translate.py`:

```python
from app.services.chat.stream import ChatEvent
from app.services.responses.translate import ResponseAccumulator

ANSWER = ChatEvent("answer", {
    "answer": "คำตอบเต็ม",
    "summary": "สรุป",
    "references": [{"number": 1, "agency_id": "a-1", "agency_name": "กรมการปกครอง", "url": None}],
    "sections": [{"agencies": [{"id": "a-1"}]}],
    "errors": [],
})
DONE = ChatEvent("done", {"session_id": "s-1", "total_ms": 1200})


def _acc() -> ResponseAccumulator:
    return ResponseAccumulator(
        response_id="resp_11111111-1111-1111-1111-111111111111",
        model="thai-citizen-guide-v5",
        conversation_id="c-1",
    )


def _drain(acc: ResponseAccumulator) -> list[dict]:
    events = [acc.created_event()]
    for chat_event in (ANSWER, DONE):
        events.extend(acc.consume(chat_event))
    return events


def test_full_event_sequence_and_order():
    assert [e["type"] for e in _drain(_acc())] == [
        "response.created",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ]


def test_sequence_numbers_are_zero_based_and_strictly_increasing():
    numbers = [e["sequence_number"] for e in _drain(_acc())]
    assert numbers == list(range(len(numbers)))


def test_the_delta_carries_the_whole_answer():
    delta = next(e for e in _drain(_acc()) if e["type"] == "response.output_text.delta")
    assert delta["delta"] == "คำตอบเต็ม"
    assert delta["output_index"] == 0
    assert delta["content_index"] == 0


def test_item_id_is_stable_across_the_stream():
    events = _drain(_acc())
    item_ids = {e["item_id"] for e in events if "item_id" in e}
    assert item_ids == {"msg_11111111-1111-1111-1111-111111111111"}


def test_completed_carries_the_final_response():
    completed = _drain(_acc())[-1]
    response = completed["response"]
    assert response["id"] == "resp_11111111-1111-1111-1111-111111111111"
    assert response["object"] == "response"
    assert response["status"] == "completed"
    assert response["model"] == "thai-citizen-guide-v5"
    assert response["output_text"] == "คำตอบเต็ม"
    assert response["output"][0]["content"][0]["text"] == "คำตอบเต็ม"
    assert response["usage"] == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def test_portal_block_carries_the_v5_extras():
    portal = _drain(_acc())[-1]["response"]["portal"]
    assert portal["conversation_id"] == "c-1"
    assert portal["summary"] == "สรุป"
    assert portal["references"][0]["agency_name"] == "กรมการปกครอง"
    assert portal["agency_ids"] == ["a-1"]
    assert portal["cached"] is False
    assert portal["stream_version"] == "v5"


def test_cached_flag_is_reported():
    acc = ResponseAccumulator(
        response_id="resp_x", model="thai-citizen-guide", conversation_id="c-1", cached=True,
    )
    acc.created_event()
    acc.consume(ANSWER)
    assert acc.final_response()["portal"]["cached"] is True


def test_degrade_case_without_summary_still_completes():
    acc = _acc()
    acc.created_event()
    acc.consume(ChatEvent("answer", {"answer": "เฉพาะคำตอบ", "sections": [], "errors": []}))
    response = acc.final_response()
    assert response["output_text"] == "เฉพาะคำตอบ"
    assert response["portal"]["summary"] == ""
    assert response["portal"]["references"] == []


def test_pipeline_progress_events_produce_nothing():
    acc = _acc()
    acc.created_event()
    for name in ("step", "intent", "routing", "agency_start", "agency_responded", "agency_verified"):
        assert acc.consume(ChatEvent(name, {"whatever": True})) == []


def test_error_event_produces_response_failed():
    acc = _acc()
    acc.created_event()
    events = acc.consume(ChatEvent("error", {"message": "upstream exploded", "code": 502}))
    assert [e["type"] for e in events] == ["response.failed"]
    response = events[0]["response"]
    assert response["status"] == "failed"
    assert response["error"]["message"] == "upstream exploded"


def test_done_after_an_error_does_not_emit_completed():
    acc = _acc()
    acc.created_event()
    acc.consume(ChatEvent("error", {"message": "boom", "code": 500}))
    assert acc.consume(DONE) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_translate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.responses.translate'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/responses/translate.py`:

```python
"""Translate portal ChatEvents into OpenAI Responses events.

Pure and transport-free: SSE, WebSocket and the non-streaming path all drive the
same accumulator, so they cannot drift.

OneChat delivers the answer as one terminal `answer` event, not token deltas, so
the stream is a correct OpenAI sequence containing a single large delta. If the
upstream ever emits incremental text, `consume()` naturally emits several
`response.output_text.delta` events with no change to any caller.
"""
import time
from typing import Any

from app.services.chat.stream import ChatEvent

_ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

# Upstream pipeline-progress events have no standard Responses counterpart.
# Injecting non-standard event types is what breaks strict SDK parsers, so they
# are dropped; clients wanting the pipeline view use /chat/stream.
_IGNORED = frozenset(
    {"step", "intent", "routing", "agency_start", "agency_responded", "agency_verified"}
)


class ResponseAccumulator:
    def __init__(
        self, response_id: str, model: str, conversation_id: str,
        *, cached: bool = False, stream_version: str = "v5",
    ):
        self.response_id = response_id
        self.item_id = "msg_" + response_id.removeprefix("resp_")
        self.model = model
        self.conversation_id = conversation_id
        self.cached = cached
        self.stream_version = stream_version
        self.created_at = int(time.time())
        self.answer = ""
        self.summary = ""
        self.references: list[dict] = []
        self.agency_ids: list[str] = []
        self.failed = False
        self.error: dict | None = None
        self._sequence = 0

    def _next(self) -> int:
        value = self._sequence
        self._sequence += 1
        return value

    def created_event(self) -> dict:
        return {
            "type": "response.created",
            "sequence_number": self._next(),
            "response": self._response_body(status="in_progress", with_output=False),
        }

    def consume(self, event: ChatEvent) -> list[dict]:
        if event.name in _IGNORED:
            return []
        if event.name == "error":
            return [self._failed(event.data.get("message", "Upstream error"))]
        if event.name == "answer":
            return self._answer_events(event.data)
        if event.name == "done":
            if self.failed:
                return []
            return [{
                "type": "response.completed",
                "sequence_number": self._next(),
                "response": self.final_response(),
            }]
        return []

    def _answer_events(self, data: dict) -> list[dict]:
        self.answer = (data.get("answer") or "").strip()
        self.summary = (data.get("summary") or "").strip()
        self.references = data.get("references") or []
        self.agency_ids = [
            agency["id"]
            for section in data.get("sections") or []
            for agency in section.get("agencies", [])
        ]
        part = {"type": "output_text", "text": self.answer, "annotations": []}
        return [
            {
                "type": "response.output_item.added",
                "sequence_number": self._next(),
                "output_index": 0,
                "item": {
                    "id": self.item_id, "type": "message", "status": "in_progress",
                    "role": "assistant", "content": [],
                },
            },
            {
                "type": "response.content_part.added",
                "sequence_number": self._next(),
                "item_id": self.item_id, "output_index": 0, "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            },
            {
                "type": "response.output_text.delta",
                "sequence_number": self._next(),
                "item_id": self.item_id, "output_index": 0, "content_index": 0,
                "delta": self.answer,
            },
            {
                "type": "response.output_text.done",
                "sequence_number": self._next(),
                "item_id": self.item_id, "output_index": 0, "content_index": 0,
                "text": self.answer,
            },
            {
                "type": "response.content_part.done",
                "sequence_number": self._next(),
                "item_id": self.item_id, "output_index": 0, "content_index": 0,
                "part": part,
            },
            {
                "type": "response.output_item.done",
                "sequence_number": self._next(),
                "output_index": 0,
                "item": {
                    "id": self.item_id, "type": "message", "status": "completed",
                    "role": "assistant", "content": [part],
                },
            },
        ]

    def _failed(self, message: str) -> dict:
        self.failed = True
        self.error = {"code": "server_error", "message": message}
        return {
            "type": "response.failed",
            "sequence_number": self._next(),
            "response": self._response_body(status="failed", with_output=False),
        }

    def failed_event(self, message: str, code: int | None = None) -> dict:
        return self._failed(message)

    def final_response(self) -> dict:
        return self._response_body(status="completed", with_output=True)

    def _response_body(self, *, status: str, with_output: bool) -> dict:
        body: dict[str, Any] = {
            "id": self.response_id,
            "object": "response",
            "created_at": self.created_at,
            "status": status,
            "model": self.model,
            "output": [],
            "output_text": self.answer if with_output else "",
            # Always zero: OneChat does not report token counts to the portal and
            # inventing them would corrupt client-side cost accounting.
            "usage": dict(_ZERO_USAGE),
            "portal": {
                "conversation_id": self.conversation_id,
                "summary": self.summary,
                "references": self.references,
                "agency_ids": self.agency_ids,
                "cached": self.cached,
                "stream_version": self.stream_version,
            },
        }
        if with_output and self.answer:
            body["output"] = [{
                "id": self.item_id, "type": "message", "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": self.answer, "annotations": []}],
            }]
        if self.error is not None:
            body["error"] = self.error
        return body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_translate.py -v`
Expected: PASS — 13 passed (2 from Task 2, 11 new)

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/responses/translate.py backend/tests/services/test_responses_translate.py
rtk git commit -m "feat(responses): translate portal events into OpenAI Responses events"
```

---

### Task 6: The HTTP endpoint (non-streaming and SSE)

**Files:**
- Create: `backend/app/routers/responses.py`
- Modify: `backend/app/main.py:140` (mount the router)
- Test: `backend/tests/routers/test_responses_http.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: `router` (APIRouter, prefix `/responses`); `async run_response(request: ResponsesRequest, *, user, background_tasks, cache=None) -> AsyncIterator[dict]` — the shared driver both HTTP and WebSocket use.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/routers/test_responses_http.py`:

```python
"""POST /api/v1/responses — the OpenAI-compatible HTTP surface."""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks

from app.models.conversation import Conversation, Message
from app.schemas.responses import ResponsesRequest
from app.routers import responses as responses_router
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent
from app.services.responses.errors import ResponsesApiError

ANSWER_DATA = {
    "answer": "คำตอบเต็ม", "summary": "สรุป",
    "references": [{"number": 1, "agency_id": "a-1", "agency_name": "กรม", "url": None}],
    "sections": [], "errors": [],
}


def _fake_live(*events: ChatEvent):
    """Replace _stream_live so no upstream HTTP call happens."""
    async def _run(plan, background_tasks):
        for event in events:
            yield event
    return _run


def _default_events(conversation_id: str):
    return (
        ChatEvent("step", {"name": "summarize"}),
        ChatEvent("answer", ANSWER_DATA),
        ChatEvent("done", {"session_id": conversation_id, "total_ms": 900}),
    )


@pytest.mark.asyncio
async def test_non_streaming_returns_a_complete_response(db):
    request = ResponsesRequest(model="thai-citizen-guide-v5", input="บัตรหาย")
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        body = await responses_router.create_response(
            request, BackgroundTasks(), user=None,
        )

    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["output_text"] == "คำตอบเต็ม"
    assert body["model"] == "thai-citizen-guide-v5"
    assert body["portal"]["summary"] == "สรุป"
    assert body["id"].startswith("resp_")

    saved = await Message.get(id=uuid.UUID(body["id"].removeprefix("resp_")))
    assert saved.role == "assistant"
    assert saved.content == "คำตอบเต็ม"


@pytest.mark.asyncio
async def test_streaming_emits_the_openai_sequence(db):
    request = ResponsesRequest(model="thai-citizen-guide", input="บัตรหาย", stream=True)
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        response = await responses_router.create_response(
            request, BackgroundTasks(), user=None,
        )
        chunks = [c async for c in response.body_iterator]

    text = "".join(c if isinstance(c, str) else c.decode() for c in chunks)
    types = [json.loads(line[6:])["type"]
             for line in text.splitlines() if line.startswith("data: ")]
    assert types == [
        "response.created", "response.output_item.added", "response.content_part.added",
        "response.output_text.delta", "response.output_text.done",
        "response.content_part.done", "response.output_item.done", "response.completed",
    ]
    assert text.rstrip().endswith("data: [DONE]")


@pytest.mark.asyncio
async def test_previous_response_id_continues_the_conversation(db):
    first = ResponsesRequest(model="thai-citizen-guide", input="หนึ่ง")
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        body = await responses_router.create_response(first, BackgroundTasks(), user=None)

    conversation_id = body["portal"]["conversation_id"]
    second = ResponsesRequest(
        model="thai-citizen-guide", input="สอง", previous_response_id=body["id"],
    )
    with patch.object(turn_stream, "ensure_session_warmed", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        second_body = await responses_router.create_response(second, BackgroundTasks(), user=None)

    assert second_body["portal"]["conversation_id"] == conversation_id
    assert second_body["id"] != body["id"]
    assert await Message.filter(conversation_id=conversation_id).count() == 4


@pytest.mark.asyncio
async def test_unknown_model_raises_a_responses_error(db):
    with pytest.raises(ResponsesApiError) as exc:
        await responses_router.create_response(
            ResponsesRequest(model="gpt-5", input="hi"), BackgroundTasks(), user=None,
        )
    assert exc.value.status == 400
    assert exc.value.param == "model"


@pytest.mark.asyncio
async def test_unknown_previous_response_id_raises_404(db):
    request = ResponsesRequest(
        model="thai-citizen-guide", input="hi", previous_response_id=f"resp_{uuid.uuid4()}",
    )
    with pytest.raises(ResponsesApiError) as exc:
        await responses_router.create_response(request, BackgroundTasks(), user=None)
    assert exc.value.code == "previous_response_not_found"


@pytest.mark.asyncio
async def test_empty_input_raises_400(db):
    with pytest.raises(ResponsesApiError):
        await responses_router.create_response(
            ResponsesRequest(model="thai-citizen-guide", input="   "),
            BackgroundTasks(), user=None,
        )


@pytest.mark.asyncio
async def test_cache_hit_is_reported_in_portal(db):
    conv = await Conversation.create(status="success")
    user_msg = await Message.create(conversation=conv, role="user", content="q")
    asst_msg = await Message.create(
        parent_id=user_msg.id, conversation=conv, role="assistant", content="cached answer"
    )

    class _Log:
        response_body = json.dumps({"answer": "cached answer"})

    with patch.object(turn_stream, "find_similar_question",
                      new=AsyncMock(return_value=(user_msg, asst_msg, _Log()))):
        body = await responses_router.create_response(
            ResponsesRequest(model="thai-citizen-guide", input="q"),
            BackgroundTasks(), user=None,
        )

    assert body["portal"]["cached"] is True
    assert body["output_text"] == "cached answer"


@pytest.mark.asyncio
async def test_one_connection_log_per_turn(db):
    from app.models.connection_log import ConnectionLog

    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events("s"))):
        await responses_router.create_response(
            ResponsesRequest(model="thai-citizen-guide", input="hi"),
            BackgroundTasks(), user=None,
        )
    assert await ConnectionLog.filter(action="query").count() == 1


@pytest.mark.asyncio
async def test_upstream_error_becomes_response_failed(db):
    request = ResponsesRequest(model="thai-citizen-guide", input="hi", stream=True)
    events = (
        ChatEvent("error", {"message": "OneChat v5 returned 502", "code": 502}),
        ChatEvent("done", {"session_id": "s", "total_ms": 0}),
    )
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*events)):
        response = await responses_router.create_response(request, BackgroundTasks(), user=None)
        chunks = [c async for c in response.body_iterator]

    text = "".join(c if isinstance(c, str) else c.decode() for c in chunks)
    types = [json.loads(line[6:])["type"]
             for line in text.splitlines() if line.startswith("data: ")]
    assert types == ["response.created", "response.failed"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/routers/test_responses_http.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.responses'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/routers/responses.py`:

```python
"""OpenAI-compatible Responses API.

    POST /api/v1/responses    stream=false → a complete Response object
                              stream=true  → OpenAI SSE
    WS   /api/v1/responses    response.create frames in, the same events out

All three transports drive one `run_response()` generator, so their wire output
cannot drift. Errors use OpenAI's envelope (services/responses/errors.py), not
the portal's.
"""
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from opentelemetry import trace

from app.auth.dependencies import get_current_user_optional
from app.models.user import User
from app.schemas.responses import ResponsesRequest
from app.services.chat.stream import ConversationNotFound, prepare_turn, run_turn
from app.services.quota import QuotaExceeded, check_global_budget, check_user_quota
from app.services.rate_limit import user_limiter
from app.config import settings
from app.services.responses.continuity import resolve_conversation, response_id_for
from app.services.responses.errors import ResponsesApiError
from app.services.responses.request import extract_query, resolve_model
from app.services.responses.translate import ResponseAccumulator

router = APIRouter(prefix="/responses", tags=["Responses"])
tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)


async def _enforce_limits(user: User | None) -> None:
    """Rate limit and quota, in OpenAI's error vocabulary."""
    if user is not None:
        result = await user_limiter.check(f"user:{user.id}", limit=settings.USER_RATE_LIMIT_RPM)
        if not result.allowed:
            raise ResponsesApiError(
                "Rate limit exceeded", type="rate_limit_error",
                code="rate_limit_exceeded", status=429,
            )
    try:
        await check_global_budget()
        if user is not None:
            await check_user_quota(user.id)
    except QuotaExceeded as e:
        raise ResponsesApiError(
            str(e), type="rate_limit_error", code="quota_exceeded", status=429,
        )


async def run_response(
    request: ResponsesRequest,
    *,
    user: User | None,
    background_tasks: BackgroundTasks | None,
    cache: dict[str, str] | None = None,
) -> AsyncIterator[dict]:
    """Drive one turn and yield OpenAI Responses events.

    Shared by every transport. `cache` is a WebSocket connection's local
    response-id → conversation-id map; None on HTTP.
    """
    await _enforce_limits(user)
    model, stream_version = resolve_model(request.model)
    query = extract_query(request.input)
    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id=request.previous_response_id,
        conversation=request.conversation,
        cache=cache,
    )

    try:
        plan = await prepare_turn(
            query=query, conversation_id=conversation_id, user=user,
            is_continuation=is_continuation,
        )
    except ConversationNotFound:
        raise ResponsesApiError(
            f"Conversation '{conversation_id}' not found",
            param="conversation", code="conversation_not_found", status=404,
        )

    # A model id that pins a version wins over CHAT_STREAM_VERSION.
    if plan.stream_version != stream_version:
        plan.stream_version = stream_version
        plan.upstream_url = (
            settings.ONECHAT_V4_URL if stream_version == "v4" else settings.ONECHAT_V5_URL
        )

    accumulator = ResponseAccumulator(
        response_id=response_id_for(plan.assistant_message_id),
        model=model,
        conversation_id=conversation_id,
        cached=plan.cached is not None,
        stream_version=plan.stream_version,
    )
    yield accumulator.created_event()

    async for chat_event in run_turn(plan, background_tasks=background_tasks):
        for event in accumulator.consume(chat_event):
            yield event

    if cache is not None:
        cache[accumulator.response_id] = conversation_id


@router.post("", summary="Create a model response (OpenAI Responses API compatible)")
async def create_response(
    body: ResponsesRequest,
    background_tasks: BackgroundTasks,
    user: User | None = Depends(get_current_user_optional),
) -> Any:
    with tracer.start_as_current_span("responses_endpoint") as span:
        span.set_attribute("stream", body.stream)

        if body.stream:
            async def sse() -> AsyncIterator[str]:
                async for event in run_response(
                    body, user=user, background_tasks=background_tasks,
                ):
                    yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                sse(), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        final = None
        async for event in run_response(body, user=user, background_tasks=background_tasks):
            if event["type"] in ("response.completed", "response.failed"):
                final = event["response"]
        if final is None:
            raise ResponsesApiError(
                "The upstream produced no answer.", type="server_error",
                code="no_answer", status=502,
            )
        return final
```

In `backend/app/main.py`, add the import alongside the other routers and mount it after `chat`:

```python
app.include_router(responses.router, prefix="/api/v1")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/routers/test_responses_http.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS — no regressions.

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/routers/responses.py backend/app/main.py backend/tests/routers/test_responses_http.py
rtk git commit -m "feat(responses): add POST /api/v1/responses with SSE streaming"
```

---

### Task 7: Auth and the role chokepoint

**Files:**
- Modify: `backend/app/auth/dependencies.py:86-100` (`_is_shared_write`)
- Test: `backend/tests/routers/test_responses_auth.py`

**Interfaces:**
- Consumes: `_is_shared_write` (existing).
- Produces: no new symbols.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/routers/test_responses_auth.py`:

```python
"""/responses is reachable by every authenticated role and by anonymous callers.

It mirrors /chat: a programmatic surface that read-restricted roles may still
use. The chokepoint (enforce_role_allowlist) must therefore allow the POST.
"""

from app.auth.dependencies import (
    _is_allowed_for_auditor,
    _is_allowed_for_basic_user,
    _is_allowed_for_viewer,
)

PATH = "/api/v1/responses"


def test_basic_user_may_post_responses():
    assert _is_allowed_for_basic_user("POST", PATH) is True


def test_viewer_may_post_responses():
    assert _is_allowed_for_viewer("POST", PATH) is True


def test_auditor_may_post_responses():
    assert _is_allowed_for_auditor("POST", PATH) is True


def test_basic_user_still_cannot_post_elsewhere():
    assert _is_allowed_for_basic_user("POST", "/api/v1/agencies") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/routers/test_responses_auth.py -v`
Expected: FAIL — three assertions fail, `assert False is True`

- [ ] **Step 3: Write the implementation**

In `backend/app/auth/dependencies.py`, extend `_is_shared_write`:

```python
    if method == "POST" and path in (
        "/api/v1/chat", "/api/v1/chat/stream", "/api/v1/responses",
    ):
        return True
```

Update that function's docstring to name the endpoint:

```python
    """Writes every authenticated role (incl. read-only ones) may perform.

    Chat (including the OpenAI-compatible /responses surface), message rating,
    own-conversation management, and the self/auth endpoints. Everything else is
    a privileged write.
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/routers/test_responses_auth.py tests/test_role_allowlist.py tests/test_basic_user_allowlist.py -v`
Expected: PASS — the new file passes and neither existing allowlist suite regresses.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/auth/dependencies.py backend/tests/routers/test_responses_auth.py
rtk git commit -m "feat(responses): allow every authenticated role through the chokepoint"
```

---

### Task 8: WebSocket session logic

The socket loop is thin plumbing; all the behaviour lives in a socket-free `WsSession` so it can be tested by direct call, matching how the rest of this codebase tests.

**Files:**
- Modify: `backend/app/config.py:83-85` and `SETTINGS_GROUPS` at line 165
- Create: `backend/app/services/responses/session.py`
- Test: `backend/tests/services/test_responses_ws_session.py`

**Interfaces:**
- Consumes: `run_response` (Task 6); `ResponsesApiError` (Task 2).
- Produces: `WsSession(user)` with `async handle_text(raw: str, send: Callable[[dict], Awaitable[None]]) -> None` and attribute `cache: dict[str, str]`; settings `RESPONSES_WS_MAX_CONNECTIONS`, `RESPONSES_WS_MAX_DURATION_SECONDS`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_responses_ws_session.py`:

```python
"""WebSocket frame handling, tested without a socket."""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.config import SETTINGS_GROUPS, settings
from app.services.chat import stream as turn_stream
from app.services.chat.stream import ChatEvent
from app.services.responses import session as ws_session
from app.services.responses.session import WsSession

ANSWER_DATA = {"answer": "คำตอบ", "summary": "", "references": [], "sections": [], "errors": []}


def _fake_live(*events: ChatEvent):
    async def _run(plan, background_tasks):
        for event in events:
            yield event
    return _run


def _default_events():
    return (
        ChatEvent("answer", ANSWER_DATA),
        ChatEvent("done", {"session_id": "s", "total_ms": 10}),
    )


class _Sink:
    def __init__(self):
        self.frames: list[dict] = []

    async def __call__(self, frame: dict) -> None:
        self.frames.append(frame)

    @property
    def types(self) -> list[str]:
        return [f["type"] for f in self.frames]


def _create(**overrides) -> str:
    payload = {"type": "response.create", "model": "thai-citizen-guide", "input": "q"}
    payload.update(overrides)
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_response_create_emits_the_full_sequence(db):
    sink = _Sink()
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
        await WsSession(user=None).handle_text(_create(), sink)

    assert sink.types == [
        "response.created", "response.output_item.added", "response.content_part.added",
        "response.output_text.delta", "response.output_text.done",
        "response.content_part.done", "response.output_item.done", "response.completed",
    ]


@pytest.mark.asyncio
async def test_two_sequential_creates_both_complete(db):
    sink = _Sink()
    session = WsSession(user=None)
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
        await session.handle_text(_create(), sink)
        await session.handle_text(_create(input="another"), sink)

    assert sink.types.count("response.completed") == 2


@pytest.mark.asyncio
async def test_the_connection_cache_serves_a_continuation(db):
    sink = _Sink()
    session = WsSession(user=None)
    with patch.object(turn_stream, "find_similar_question", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
        await session.handle_text(_create(), sink)

    first_id = sink.frames[-1]["response"]["id"]
    conversation_id = sink.frames[-1]["response"]["portal"]["conversation_id"]
    assert session.cache[first_id] == conversation_id

    with patch.object(turn_stream, "ensure_session_warmed", new=AsyncMock(return_value=None)), \
         patch.object(turn_stream, "_stream_live", new=_fake_live(*_default_events())):
        await session.handle_text(_create(previous_response_id=first_id), sink)

    assert sink.frames[-1]["response"]["portal"]["conversation_id"] == conversation_id


@pytest.mark.asyncio
async def test_generate_false_warms_without_generating(db):
    from app.models.conversation import Conversation, Message

    conv = await Conversation.create(status="success")
    await Message.create(conversation=conv, role="user", content="q")
    sink = _Sink()
    warm = AsyncMock(return_value=None)

    # `_warm` calls the name bound in session.py, not the one in stream.py.
    with patch.object(ws_session, "ensure_session_warmed", new=warm):
        await WsSession(user=None).handle_text(
            _create(generate=False, conversation=str(conv.id)), sink
        )

    assert warm.await_count == 1
    assert sink.types == []
    assert await Message.filter(conversation_id=conv.id).count() == 1


@pytest.mark.asyncio
async def test_unknown_previous_response_id_errors_without_closing(db):
    sink = _Sink()
    await WsSession(user=None).handle_text(
        _create(previous_response_id=f"resp_{uuid.uuid4()}"), sink
    )
    assert sink.types == ["error"]
    assert sink.frames[0]["error"]["code"] == "previous_response_not_found"


@pytest.mark.asyncio
async def test_malformed_json_errors_without_closing(db):
    sink = _Sink()
    await WsSession(user=None).handle_text("{not json", sink)
    assert sink.types == ["error"]
    assert sink.frames[0]["error"]["type"] == "invalid_request_error"


@pytest.mark.asyncio
async def test_unknown_frame_type_is_rejected(db):
    sink = _Sink()
    await WsSession(user=None).handle_text(json.dumps({"type": "session.update"}), sink)
    assert sink.types == ["error"]
    assert "response.create" in sink.frames[0]["error"]["message"]


def test_ws_settings_are_registered():
    assert settings.RESPONSES_WS_MAX_CONNECTIONS == 100
    assert settings.RESPONSES_WS_MAX_DURATION_SECONDS == 3600
    assert "RESPONSES_WS_MAX_CONNECTIONS" in SETTINGS_GROUPS["Chat"]
    assert "RESPONSES_WS_MAX_DURATION_SECONDS" in SETTINGS_GROUPS["Chat"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_ws_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.responses.session'`

- [ ] **Step 3: Add the settings**

In `backend/app/config.py`, alongside the other chat settings (near `USER_RATE_LIMIT_RPM` at line 83):

```python
    RESPONSES_WS_MAX_CONNECTIONS: int = 100
    RESPONSES_WS_MAX_DURATION_SECONDS: int = 3600
```

Then add both names to the `"Chat"` list in `SETTINGS_GROUPS` (line ~170). If no `"Chat"` group exists, add them to the group that already holds `USER_RATE_LIMIT_RPM` and use that group's name in the test above instead.

- [ ] **Step 4: Write the implementation**

Create `backend/app/services/responses/session.py`:

```python
"""Per-connection WebSocket logic for the Responses API, without the socket.

The transport passes raw text in and a `send` callable out, so the whole
protocol is testable by direct call. Sequencing is by construction: the router
awaits `handle_text` before reading the next frame, so exactly one response is
ever in flight and additional `response.create` frames queue in the socket
buffer — which is what "no multiplexing" means upstream.
"""
import json
import logging
from typing import Awaitable, Callable

from app.models.user import User
from app.schemas.responses import ResponsesRequest
from app.services.chat.stream import ConversationNotFound
from app.services.responses.continuity import resolve_conversation
from app.services.responses.errors import ResponsesApiError
from app.services.session import ensure_session_warmed
from app.config import settings

logger = logging.getLogger(__name__)

Send = Callable[[dict], Awaitable[None]]


class WsSession:
    """One WebSocket connection's state: the caller and its recent responses."""

    def __init__(self, user: User | None):
        self.user = user
        # response id → conversation id for this connection, mirroring OpenAI's
        # connection-local cache. A miss falls back to the database.
        self.cache: dict[str, str] = {}

    async def handle_text(self, raw: str, send: Send) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            await send(_error_frame(ResponsesApiError("Frame is not valid JSON.")))
            return

        if not isinstance(payload, dict) or payload.get("type") != "response.create":
            await send(_error_frame(ResponsesApiError(
                "Unsupported frame type; this endpoint accepts `response.create` only.",
                param="type",
            )))
            return

        try:
            request = ResponsesRequest.model_validate(payload)
            if not request.generate:
                await self._warm(request)
                return
            await self._generate(request, send)
        except ResponsesApiError as e:
            await send(_error_frame(e))

    async def _warm(self, request: ResponsesRequest) -> None:
        """`generate: false` — resolve and warm the session, emit nothing."""
        from app.models.conversation import Conversation

        conversation_id, is_continuation = await resolve_conversation(
            previous_response_id=request.previous_response_id,
            conversation=request.conversation,
            cache=self.cache,
        )
        if not is_continuation:
            return
        conv = await Conversation.filter(id=conversation_id).first()
        if conv is None:
            raise ResponsesApiError(
                f"Conversation '{conversation_id}' not found",
                param="conversation", code="conversation_not_found", status=404,
            )
        try:
            await ensure_session_warmed(
                conv, settings.ONECHAT_V3_URL, settings.MCP_ENDPOINT_URL
            )
        except Exception:
            logger.warning("Warm-up failed for conversation %s", conversation_id)

    async def _generate(self, request: ResponsesRequest, send: Send) -> None:
        from app.routers.responses import run_response

        async for event in run_response(
            request, user=self.user, background_tasks=None, cache=self.cache,
        ):
            await send(event)


def _error_frame(error: ResponsesApiError) -> dict:
    return {"type": "error", **error.envelope()}
```

The `run_response` import is function-local: `routers/responses.py` imports this module for the WebSocket route in Task 9, and a module-level import would be circular.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/services/test_responses_ws_session.py -v`
Expected: PASS — 8 passed

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/config.py backend/app/services/responses/session.py backend/tests/services/test_responses_ws_session.py
rtk git commit -m "feat(responses): add WebSocket session logic and its settings"
```

---

### Task 9: The WebSocket route

**Files:**
- Modify: `backend/app/routers/responses.py` (append the route)
- Test: `backend/tests/routers/test_responses_ws_route.py`

**Interfaces:**
- Consumes: `WsSession` (Task 8); `_resolve_token` from `app/auth/dependencies.py`.
- Produces: `responses_websocket(websocket)`; `_connections` (a `_ConnectionRegistry` instance) with `acquire() -> bool` / `release()`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/routers/test_responses_ws_route.py`:

```python
"""The socket loop: connection cap, auth resolution, duration cap."""

import pytest

from app.config import settings
from app.routers.responses import _ConnectionRegistry, _ws_user


@pytest.fixture
def restore_cap():
    original = settings.RESPONSES_WS_MAX_CONNECTIONS
    yield
    settings.RESPONSES_WS_MAX_CONNECTIONS = original


class _FakeSocket:
    def __init__(self, headers: dict[str, str] | None = None):
        self.headers = headers or {}


def test_registry_admits_up_to_the_cap(restore_cap):
    settings.RESPONSES_WS_MAX_CONNECTIONS = 2
    registry = _ConnectionRegistry()
    assert registry.acquire() is True
    assert registry.acquire() is True
    assert registry.acquire() is False


def test_registry_frees_a_slot_on_release(restore_cap):
    settings.RESPONSES_WS_MAX_CONNECTIONS = 1
    registry = _ConnectionRegistry()
    assert registry.acquire() is True
    assert registry.acquire() is False
    registry.release()
    assert registry.acquire() is True


def test_release_never_goes_negative(restore_cap):
    settings.RESPONSES_WS_MAX_CONNECTIONS = 1
    registry = _ConnectionRegistry()
    registry.release()
    registry.release()
    assert registry.acquire() is True
    assert registry.acquire() is False


@pytest.mark.asyncio
async def test_missing_authorization_is_anonymous(db):
    assert await _ws_user(_FakeSocket()) is None


@pytest.mark.asyncio
async def test_non_bearer_authorization_is_anonymous(db):
    assert await _ws_user(_FakeSocket({"authorization": "Basic abc"})) is None


@pytest.mark.asyncio
async def test_invalid_token_is_anonymous_not_an_exception(db):
    assert await _ws_user(_FakeSocket({"authorization": "Bearer tcg_bogus"})) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/routers/test_responses_ws_route.py -v`
Expected: FAIL — `ImportError: cannot import name '_ConnectionRegistry' from 'app.routers.responses'`

- [ ] **Step 3: Write the implementation**

Append to `backend/app/routers/responses.py`:

```python
# ─── WebSocket mode ───────────────────────────────────────────────────────────


class _ConnectionRegistry:
    """Caps concurrent sockets.

    An endpoint that allows anonymous callers and holds hour-long connections is
    otherwise an unbounded resource sink.
    """

    def __init__(self) -> None:
        self._open = 0

    def acquire(self) -> bool:
        if self._open >= settings.RESPONSES_WS_MAX_CONNECTIONS:
            return False
        self._open += 1
        return True

    def release(self) -> None:
        self._open = max(0, self._open - 1)


_connections = _ConnectionRegistry()


async def _ws_user(websocket) -> User | None:
    """Resolve the caller from the Authorization header; anonymous on anything else.

    Browsers cannot set headers on a WebSocket — browser clients should use the
    SSE transport. There is deliberately no query-parameter token fallback: it
    would leak API keys into access logs.
    """
    header = websocket.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        return await _resolve_token(header[7:])
    except Exception:
        return None


@router.websocket("")
async def responses_websocket(websocket: WebSocket) -> None:
    if not _connections.acquire():
        await websocket.close(code=1013)  # try again later
        return
    await websocket.accept()

    session = WsSession(user=await _ws_user(websocket))
    deadline = time.monotonic() + settings.RESPONSES_WS_MAX_DURATION_SECONDS

    async def send(frame: dict) -> None:
        await websocket.send_text(json.dumps(frame, ensure_ascii=False))

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await send(_connection_limit_frame())
                await websocket.close(code=1000)
                return
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
            except asyncio.TimeoutError:
                await send(_connection_limit_frame())
                await websocket.close(code=1000)
                return
            # Awaited before the next receive: one response in flight at a time,
            # additional frames queue in the socket buffer. No multiplexing.
            await session.handle_text(raw, send)
    except WebSocketDisconnect:
        return
    finally:
        _connections.release()


def _connection_limit_frame() -> dict:
    return {
        "type": "error",
        **ResponsesApiError(
            "Responses websocket connection limit reached (60 minutes). "
            "Create a new websocket connection to continue.",
            type="invalid_request_error",
            code="websocket_connection_limit_reached",
        ).envelope(),
    }
```

Extend the imports at the top of `routers/responses.py`:

```python
import asyncio
import time

from fastapi import WebSocket, WebSocketDisconnect

from app.auth.dependencies import _resolve_token, get_current_user_optional
from app.services.responses.session import WsSession
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/routers/test_responses_ws_route.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS — no regressions.

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/routers/responses.py backend/tests/routers/test_responses_ws_route.py
rtk git commit -m "feat(responses): add the WebSocket transport"
```

---

### Task 10: nginx WebSocket support

Without this the handshake 400s in every deployed environment, and an idle socket dies at 5 minutes.

**Files:**
- Modify: `default.conf`

**Interfaces:** none.

- [ ] **Step 1: Add the upgrade map and the WebSocket-aware locations**

In `default.conf`, insert above the `server {` block (line 7). `conf.d/*.conf` is included in nginx's `http` context, so a `map` is legal at the top of this file:

```nginx
# A bare `Connection "upgrade"` on /api would break keep-alive for every ordinary
# API request, so the header is derived from the client's Upgrade header.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
```

In the existing `location ~ ^/(api|sse|messages|mcp|docs|redoc|openapi.json)` block, add two headers after `proxy_set_header X-Forwarded-Host $http_host;`:

```nginx
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection $connection_upgrade;
```

Then add an exact-match location *above* that regex location (nginx matches exact `=` locations first regardless of order, but keeping it above documents intent):

```nginx
    # OpenAI Responses API. The WebSocket transport holds a connection for up to
    # 60 minutes (RESPONSES_WS_MAX_DURATION_SECONDS), so the 300s read timeout
    # the other /api routes use would kill an idle socket well before the cap.
    location = /api/v1/responses {
        proxy_pass         http://backend:8080;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-Host $http_host;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection $connection_upgrade;

        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 3700s;
        proxy_send_timeout 3700s;
    }
```

Update the routing contract comment at the top of the file so it stays the single source of truth:

```nginx
#   /api,/sse,/messages,/mcp,/docs,/redoc,/openapi.json -> backend:8080
#     (/api/v1/responses also serves a WebSocket; see the exact-match location)
```

- [ ] **Step 2: Verify the config parses**

Run: `rtk docker compose exec nginx nginx -t` (if the stack is running), or
`rtk docker run --rm -v "$PWD/default.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t`
Expected: `syntax is ok` / `test is successful`

If the stack is not running and Docker is unavailable, skip this step and note it — Task 11's deploy rebuild will surface a syntax error.

- [ ] **Step 3: Commit**

```bash
rtk git add default.conf
rtk git commit -m "feat(nginx): proxy WebSocket upgrades to /api/v1/responses"
```

---

### Task 11: Documentation

**Files:**
- Create: `spec/openai-responses.md`
- Modify: `docs/quickstart.md`
- Modify: `CONTEXT.md`

**Interfaces:** none.

- [ ] **Step 1: Write `spec/openai-responses.md`**

Create the file with the wire contract, mirroring the role `spec/v5.md` plays. Do not invent shapes — copy each one from the code that now exists, so the spec cannot drift from the implementation:

| Section | Copy the exact shape from |
|---|---|
| Accepted `model` ids → upstream | `MODEL_IDS` in `app/services/responses/request.py` |
| `input` forms (string, array, multi-part) | the cases in `tests/services/test_responses_request.py` |
| `previous_response_id` / `conversation` | `app/services/responses/continuity.py` |
| The 8-event streaming sequence | `ResponseAccumulator._answer_events` + `created_event` + `consume` in `app/services/responses/translate.py`; the ordering assertion in `tests/services/test_responses_translate.py` |
| The `Response` object and `portal` block | `ResponseAccumulator._response_body` |
| Error envelope + codes | `ResponsesApiError.envelope()`; the codes are `previous_response_not_found`, `conversation_not_found`, `websocket_connection_limit_reached`, `rate_limit_exceeded`, `quota_exceeded` |
| WebSocket frames incl. `generate: false` | `WsSession.handle_text` in `app/services/responses/session.py` and `_connection_limit_frame` in `app/routers/responses.py` |

Give each one a concrete JSON example, as `spec/v5.md` does.

State the three deviations from OpenAI explicitly, each with its reason:

```markdown
## Deviations from the OpenAI contract

| Deviation | Reason |
|---|---|
| `store` is accepted but ignored — every turn is persisted | The portal records turns for analytics, audit and the similarity cache. A client expecting zero retention must not use this endpoint. |
| `usage` is always zero | OneChat does not report token counts to the portal; inventing them would corrupt client-side cost accounting. |
| Pipeline progress (`step`, `agency_*`) is not surfaced | No standard Responses event carries it, and non-standard SSE event types break strict SDK parsers. Use `/chat/stream` for the pipeline view. |
| A non-standard top-level `portal` object carries summary/references/agency ids | OpenAI types `metadata` as a flat string map that the SDK validates; structured data there breaks real clients. SDK models ignore unknown top-level keys. |
```

- [ ] **Step 2: Add the consumer section to `docs/quickstart.md`**

Append a section following the file's existing structure and tone:

````markdown
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
````

- [ ] **Step 3: Update `CONTEXT.md`**

Make these edits so the orientation doc stays accurate:

1. In the **Backend → Package map** `routers/` list, change "18 REST routers" to "19 REST routers" and add `responses` to the list.
2. Under **Request flow (chat)**, add a paragraph after the numbered list:

```markdown
`POST /api/v1/responses` is an **OpenAI Responses API compatible** surface over the same
pipeline (`routers/responses.py`), in three transports: HTTP non-streaming, HTTP SSE, and a
WebSocket on the same path. It shares one turn implementation with `/chat/stream` via
`services/chat/stream.py` (`prepare_turn` / `run_turn`), and translates to OpenAI's wire
format in `services/responses/`. `store` is accepted but ignored, `usage` is always zero, and
pipeline progress events are not surfaced. See `spec/openai-responses.md`.
```

3. In the **`services/`** bullet, add `responses/` (request mapping, continuity, event translation, WebSocket session) and note that `chat/` now contains `stream` (the shared turn pipeline).
4. In **Auth & RBAC**, extend the sentence about the chokepoint to note that `POST /api/v1/responses` is a shared write allowed for every authenticated role, and that the WebSocket route is not covered by the HTTP chokepoint (it resolves auth itself).
5. In the **nginx routing** block, note that `/api/v1/responses` also serves a WebSocket and has its own extended read timeout.
6. In **Documentation & specs map**, add `spec/openai-responses.md`.

- [ ] **Step 4: Verify the full suite and commit**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS — everything green.

```bash
rtk git add spec/openai-responses.md docs/quickstart.md CONTEXT.md
rtk git commit -m "docs: document the OpenAI Responses API endpoint"
```

---

## Done criteria

- [ ] `cd backend && .venv/bin/pytest -q` passes with no regressions in the pre-existing suite.
- [ ] `POST /api/v1/responses` works from the official OpenAI Python SDK, streaming and not.
- [ ] `wss://<host>/api/v1/responses` completes a `response.create` round trip.
- [ ] `/chat/stream` and the SPA are byte-identical in behaviour to before Task 1.
- [ ] `CONTEXT.md` is updated and committed.
- [ ] PR into `dev` (after `feat/onechat-v5` lands there); on merge to `main`, rebuild docker compose.
