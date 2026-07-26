# Persist Agent-Step Pipeline Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist a snapshot of the AI-agent pipeline progress (steps + per-agency statuses + errors) with each assistant message and render it as a shared collapsible card in both live chat and history.

**Architecture:** Backend collects the streamed `step`/`agency_*` events during `/chat/stream`, folds them into a snapshot via a pure function, and stores it in the existing `Message.agent_steps` JSON column. History already returns that field. The frontend adds a shared `AgentStepsCard` inside `AssistantMessageContent`, fed by a persisted snapshot (history, normalized) or a live snapshot built from the terminal `StreamingState`.

**Tech Stack:** Backend — Python, FastAPI, Tortoise ORM, pytest/pytest-asyncio (SQLite in-memory). Frontend — React, TypeScript, Vitest, Testing Library.

## Global Constraints

- TDD mandatory: failing test → confirm fail → minimal code → confirm pass. No exceptions.
- Google style guides; American English naming; imports sorted by path.
- Prefix shell commands with `rtk`.
- Work on branch `feat/persist-agent-steps` (already created). Commit after each task.
- Path coverage: `/chat/stream` only. Do **not** touch the Responses API path.
- Reuse the `Message.agent_steps` column — no DB migration.
- Persisted snapshot is snake_case; the frontend normalizes to camelCase.
- Card order in `AssistantMessageContent`: Thinking → answer bubble → Summary → Agent steps.
- Card is collapsible, collapsed by default.

---

## Snapshot shapes (referenced by multiple tasks)

**Persisted (backend, snake_case)** — stored in `agent_steps`, or `[]` when empty:
```jsonc
{
  "steps":    [{ "name": "discover", "ms": 1200 }],
  "agencies": [{ "id": "land", "name": "กรมที่ดิน", "status": "passed",
                 "error_type": null, "relevance_score": 0.9, "section_label": "ค่าธรรมเนียม" }],
  "errors":   [{ "agency": "foo", "name": "Foo", "error_type": "timeout", "message": "..." }]
}
```

**Frontend (camelCase)** — `AgentStepsSnapshot`:
```ts
interface AgentStepsSnapshot {
  steps: { name: string; ms: number | null }[];
  agencies: { id: string; name: string | null; status: AgencyStatus;
    errorType?: string | null; relevanceScore?: number | null; sectionLabel?: string | null }[];
  errors: { agency: string; name: string; errorType: string; message: string }[];
}
```

---

## Task 1: Backend — pure pipeline-snapshot builder

**Files:**
- Create: `backend/app/services/chat/pipeline_snapshot.py`
- Test: `backend/tests/services/test_pipeline_snapshot.py`

**Interfaces:**
- Produces: `build_pipeline_snapshot(events: list[tuple[str, dict]], errors: list) -> dict | list`
  — folds `step`/`agency_start`/`agency_responded`/`agency_verified` events into the persisted
  snapshot dict; returns `[]` when nothing was captured.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_pipeline_snapshot.py
from app.services.chat.pipeline_snapshot import build_pipeline_snapshot


def test_empty_events_return_empty_list():
    assert build_pipeline_snapshot([], []) == []


def test_folds_steps_agencies_and_errors():
    events = [
        ("step", {"name": "discover", "status": "running"}),
        ("step", {"name": "discover", "status": "done", "ms": 1200}),
        ("agency_start", {"agency_id": "land", "agency_name": "กรมที่ดิน",
                          "query": "q", "section_label": "fees"}),
        ("agency_responded", {"agency_id": "land", "status": "ok", "error_type": None}),
        ("agency_verified", {"agency_id": "land", "status": "passed", "relevance_score": 0.9}),
    ]
    snap = build_pipeline_snapshot(events, [{"agency": "x", "name": "X",
                                             "error_type": "timeout", "message": "m"}])
    assert snap["steps"] == [{"name": "discover", "ms": 1200}]
    assert snap["agencies"] == [{
        "id": "land", "name": "กรมที่ดิน", "status": "passed",
        "error_type": None, "relevance_score": 0.9, "section_label": "fees",
    }]
    assert snap["errors"] == [{"agency": "x", "name": "X",
                               "error_type": "timeout", "message": "m"}]


def test_responded_error_sets_error_type():
    events = [
        ("agency_start", {"agency_id": "a", "agency_name": "A"}),
        ("agency_responded", {"agency_id": "a", "status": "error", "error_type": "http_500"}),
    ]
    snap = build_pipeline_snapshot(events, [])
    assert snap["agencies"][0]["status"] == "error"
    assert snap["agencies"][0]["error_type"] == "http_500"


def test_bare_step_without_status_is_kept_as_done():
    snap = build_pipeline_snapshot([("step", {"name": "summarize"})], [])
    assert snap["steps"] == [{"name": "summarize", "ms": None}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && rtk pytest tests/services/test_pipeline_snapshot.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.chat.pipeline_snapshot`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/chat/pipeline_snapshot.py
"""Fold streamed pipeline events into a persistable snapshot.

Mirrors the frontend reducer (useChatStream / chatHelpers): the terminal state
of the pipeline steps and per-agency statuses, stored on Message.agent_steps so
history can show how an answer was produced. Pure — no I/O, no ORM.
"""


def build_pipeline_snapshot(events: list[tuple[str, dict]], errors: list) -> dict | list:
    """Return the snapshot dict, or [] when no pipeline data was captured."""
    step_order: list[str] = []
    step_ms: dict[str, int | None] = {}
    for name, data in events:
        if name != "step":
            continue
        step_name = data.get("name")
        if step_name is None:
            continue
        if step_name not in step_ms:
            step_order.append(step_name)
        if data.get("status") != "running":
            step_ms[step_name] = data.get("ms")
        else:
            step_ms.setdefault(step_name, None)

    agencies: dict[str, dict] = {}
    for name, data in events:
        if name not in ("agency_start", "agency_responded", "agency_verified"):
            continue
        agency_id = data.get("agency_id")
        if agency_id is None:
            continue
        entry = agencies.setdefault(agency_id, {
            "id": agency_id, "name": data.get("agency_name"), "status": "running",
            "error_type": None, "relevance_score": None,
            "section_label": data.get("section_label"),
        })
        if data.get("agency_name"):
            entry["name"] = data["agency_name"]
        if name == "agency_responded":
            entry["status"] = "ok" if data.get("status") == "ok" else "error"
            entry["error_type"] = data.get("error_type")
        elif name == "agency_verified":
            entry["status"] = data.get("status")
            entry["relevance_score"] = data.get("relevance_score")

    steps = [{"name": n, "ms": step_ms[n]} for n in step_order]
    agency_list = list(agencies.values())
    error_list = list(errors or [])
    if not steps and not agency_list and not error_list:
        return []
    return {"steps": steps, "agencies": agency_list, "errors": error_list}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && rtk pytest tests/services/test_pipeline_snapshot.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/chat/pipeline_snapshot.py backend/tests/services/test_pipeline_snapshot.py
rtk git commit -m "feat(chat): pure pipeline-snapshot builder for agent steps"
```

---

## Task 2: Backend — persist `agent_steps` through `save_turn`

**Files:**
- Modify: `backend/app/services/chat/turn.py:20-88`
- Test: `backend/tests/services/test_save_turn_agent_steps.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `save_turn(..., agent_steps: dict | list | None = None)` — writes it to the assistant
  `Message.agent_steps` (defaults to `[]`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_save_turn_agent_steps.py
import pytest

from app.models.conversation import Message
from app.services.chat.turn import save_turn


@pytest.mark.usefixtures("db")
async def test_save_turn_persists_agent_steps():
    snapshot = {"steps": [{"name": "discover", "ms": 10}], "agencies": [], "errors": []}
    saved = await save_turn(
        query="q", conversation_id="c1", answer="a", references=[], category=None,
        agency_ids=[], response_time=1, user=None, succeeded=True, agent_steps=snapshot,
    )
    msg = await Message.get(id=saved.assistant_message_id)
    assert msg.agent_steps == snapshot


@pytest.mark.usefixtures("db")
async def test_save_turn_defaults_agent_steps_to_empty_list():
    saved = await save_turn(
        query="q", conversation_id="c2", answer="a", references=[], category=None,
        agency_ids=[], response_time=1, user=None, succeeded=True,
    )
    msg = await Message.get(id=saved.assistant_message_id)
    assert msg.agent_steps == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && rtk pytest tests/services/test_save_turn_agent_steps.py -v`
Expected: FAIL — `save_turn() got an unexpected keyword argument 'agent_steps'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/chat/turn.py`, add the parameter to the signature (after `summary_references`):

```python
    summary_references: list | None = None,
    agent_steps: dict | list | None = None,
    title: str | None = None,
```

And pass it into the assistant `Message.create(...)` (add one line):

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
            agent_steps=agent_steps if agent_steps is not None else [],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && rtk pytest tests/services/test_save_turn_agent_steps.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/chat/turn.py backend/tests/services/test_save_turn_agent_steps.py
rtk git commit -m "feat(chat): thread agent_steps through save_turn"
```

---

## Task 3: Backend — capture events in the stream and expose via history

**Files:**
- Modify: `backend/app/services/chat/stream.py` (`_stream_live`, `_replay_cached`, `_persist`)
- Test: `backend/tests/routers/test_chat_stream_agent_steps.py`

**Interfaces:**
- Consumes: `build_pipeline_snapshot` (Task 1), `save_turn(agent_steps=...)` (Task 2).
- Produces: streamed turns persist `agent_steps`; the existing `GET /history/{id}/messages`
  endpoint returns it unchanged.

- [ ] **Step 1: Write the failing test** (mirrors `test_chat_stream_upstream.py`'s stubbed upstream)

```python
# backend/tests/routers/test_chat_stream_agent_steps.py
"""A streamed turn persists a pipeline snapshot into Message.agent_steps."""
import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tortoise import Tortoise
from unittest.mock import patch

from app.errors import register_error_handlers
from app.models.conversation import Message
from app.routers import chat as chat_router
from app.services.chat import stream as turn_stream
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


def _stub(body: str):
    async def handler(request: httpx.Request) -> httpx.Response:
        async def gen():
            yield body.encode()
        return httpx.Response(200, content=gen())
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    return patch.object(turn_stream, "get_client", lambda version=None: client)


def _events(text: str):
    out = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        name, data = "message", None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        out.append({"event": name, "data": data})
    return out


def test_streamed_turn_persists_agent_steps():
    body = (
        'event: step\ndata: {"name": "discover", "status": "done", "ms": 1200}\n\n'
        'event: agency_start\ndata: {"agency_id": "land", "agency_name": "กรมที่ดิน"}\n\n'
        'event: agency_verified\ndata: {"agency_id": "land", "status": "passed", "relevance_score": 0.9}\n\n'
        'event: answer\ndata: {"answer": "คำตอบ", "summary": "", "references": []}\n\n'
        'event: done\ndata: {"session_id": "s1", "total_ms": 42}\n\n'
    )
    with _stub(body), TestClient(_app()) as client:
        r = client.post("/api/v1/chat/stream", json={"query": "q"})
        message_id = _events(r.text)[-1]["data"]["message_id"]

        async def _fetch():
            return await Message.get(id=message_id)

        saved = client.portal.call(_fetch)

    assert saved.agent_steps["steps"] == [{"name": "discover", "ms": 1200}]
    assert saved.agent_steps["agencies"][0]["id"] == "land"
    assert saved.agent_steps["agencies"][0]["status"] == "passed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && rtk pytest tests/routers/test_chat_stream_agent_steps.py -v`
Expected: FAIL — `saved.agent_steps` is `[]`, so the `["steps"]` subscript raises `TypeError`
(list indices) / assertion fails.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/chat/stream.py`:

Add the import near the other service imports:
```python
from app.services.chat.pipeline_snapshot import build_pipeline_snapshot
```

In `_stream_live`, collect pipeline events. Add before the `try:` loop:
```python
    pipeline_events: list[tuple[str, dict]] = []
```
Inside the `async for event_name, event_data in ...` loop, right after the `elif event_name == "done":` block and before the tracer span, capture the pipeline events:
```python
            elif event_name in ("step", "agency_start", "agency_responded", "agency_verified"):
                pipeline_events.append((event_name, event_data))
```
Change the `_persist(...)` call in `_stream_live` to forward them:
```python
        assistant_id = await _persist(
            plan, answer_data=answer_data, session_id=session_id, total_ms=total_ms,
            latency_ms=log_latency_ms, thread_name=thread_name,
            background_tasks=background_tasks, pipeline_events=pipeline_events,
        )
```
Change the `_persist(...)` call in `_replay_cached` to pass an empty list:
```python
    assistant_id = await _persist(
        plan, answer_data=answer_data, session_id=None,
        total_ms=0, latency_ms=0, thread_name=None,
        background_tasks=background_tasks, pipeline_events=[],
    )
```
Update `_persist`'s signature and body:
```python
async def _persist(
    plan: TurnPlan, *, answer_data: dict, session_id: str | None, total_ms: int | None,
    latency_ms: int, thread_name: str | None, background_tasks: BackgroundTasks | None,
    pipeline_events: list[tuple[str, dict]],
) -> Any:
    ...
    errors = answer_data.get("errors", [])
    ...
    agent_steps = build_pipeline_snapshot(pipeline_events, errors)

    saved = await save_turn(
        query=plan.query, conversation_id=plan.conversation_id, answer=answer,
        references=[], category=None, agency_ids=agency_ids,
        response_time=response_time, user=plan.user, succeeded=bool(answer),
        external_session_id=session_id, errors=errors, summary=summary,
        summary_references=summary_references, title=thread_name,
        assistant_message_id=plan.assistant_message_id, agent_steps=agent_steps,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && rtk pytest tests/routers/test_chat_stream_agent_steps.py tests/routers/test_chat_stream_upstream.py -v`
Expected: PASS (new test + the existing upstream tests still green).

- [ ] **Step 5: Run the backend suite to check for regressions**

Run: `cd backend && rtk pytest -q`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/services/chat/stream.py backend/tests/routers/test_chat_stream_agent_steps.py
rtk git commit -m "feat(chat): capture pipeline events and persist snapshot on stream"
```

---

## Task 4: Frontend — snapshot type + live builder

**Files:**
- Modify: `frontend/src/shared/types/chat.ts` (add `AgentStepsSnapshot`, add `ChatMessage.pipeline`)
- Modify: `frontend/src/features/chat/chatHelpers.ts` (add `buildAgentStepsSnapshot`, set `pipeline`)
- Test: `frontend/src/features/chat/chatHelpers.test.ts` (add a describe block)

**Interfaces:**
- Produces:
  - `AgentStepsSnapshot` (shape above) exported from `shared/types/chat.ts`.
  - `ChatMessage.pipeline?: AgentStepsSnapshot | null`.
  - `buildAgentStepsSnapshot(state: StreamingState): AgentStepsSnapshot | null`.

- [ ] **Step 1: Write the failing test** (append to `chatHelpers.test.ts`)

```ts
import { buildAgentStepsSnapshot } from './chatHelpers';
import { INITIAL_STREAMING_STATE } from './chatHelpers';

describe('buildAgentStepsSnapshot', () => {
  it('returns null when nothing was captured', () => {
    expect(buildAgentStepsSnapshot(INITIAL_STREAMING_STATE)).toBeNull();
  });

  it('captures done steps, agency statuses, and errors', () => {
    const state = {
      ...INITIAL_STREAMING_STATE,
      pipelineSteps: [
        { name: 'discover', status: 'done', ms: 1200 },
        { name: 'invoke', status: 'running', ms: null },
      ],
      agencyStatuses: {
        land: { agencyId: 'land', agencyName: 'กรมที่ดิน', query: 'q',
                sectionLabel: 'fees', status: 'passed', relevanceScore: 0.9 },
      },
      errors: [{ agency: 'x', name: 'X', errorType: 'timeout', message: 'm' }],
    } as never;
    const snap = buildAgentStepsSnapshot(state)!;
    expect(snap.steps).toEqual([{ name: 'discover', ms: 1200 }]);
    expect(snap.agencies[0]).toMatchObject({ id: 'land', status: 'passed', relevanceScore: 0.9 });
    expect(snap.errors[0]).toMatchObject({ errorType: 'timeout' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && rtk vitest run src/features/chat/chatHelpers.test.ts`
Expected: FAIL — `buildAgentStepsSnapshot` is not exported.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/shared/types/chat.ts`, add after `SummaryReference` (and reuse existing `AgencyStatus`):
```ts
export interface AgentStepsSnapshot {
  steps: { name: string; ms: number | null }[];
  agencies: {
    id: string; name: string | null; status: AgencyStatus;
    errorType?: string | null; relevanceScore?: number | null; sectionLabel?: string | null;
  }[];
  errors: { agency: string; name: string; errorType: string; message: string }[];
}
```
Add to `ChatMessage` (in the same file):
```ts
  pipeline?: AgentStepsSnapshot | null;
```
In `frontend/src/features/chat/chatHelpers.ts`, add the import of the type and the builder:
```ts
import type { AgentStepsSnapshot } from '@/shared/types/chat';

export function buildAgentStepsSnapshot(state: StreamingState): AgentStepsSnapshot | null {
  const steps = state.pipelineSteps
    .filter((s) => s.status === 'done')
    .map((s) => ({ name: s.name, ms: s.ms }));
  const agencies = Object.values(state.agencyStatuses).map((a) => ({
    id: a.agencyId, name: a.agencyName, status: a.status,
    errorType: a.errorType ?? null, relevanceScore: a.relevanceScore ?? null,
    sectionLabel: a.sectionLabel ?? null,
  }));
  const errors = state.errors.map((e) => ({
    agency: e.agency, name: e.name, errorType: e.errorType, message: e.message,
  }));
  if (!steps.length && !agencies.length && !errors.length) return null;
  return { steps, agencies, errors };
}
```
In `buildAiMessageFromState`, add one line to the returned object (keep `agentSteps` as-is):
```ts
    agentSteps: buildAgentStepsFromStreaming(state),
    pipeline: buildAgentStepsSnapshot(state),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && rtk vitest run src/features/chat/chatHelpers.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/shared/types/chat.ts frontend/src/features/chat/chatHelpers.ts frontend/src/features/chat/chatHelpers.test.ts
rtk git commit -m "feat(chat): AgentStepsSnapshot type and live builder"
```

---

## Task 5: Frontend — persisted-snapshot normalizer

**Files:**
- Create: `frontend/src/shared/lib/agentSteps.ts`
- Test: `frontend/src/shared/lib/agentSteps.test.ts`

**Interfaces:**
- Consumes: `AgentStepsSnapshot` type (Task 4).
- Produces: `toAgentStepsSnapshot(raw: unknown): AgentStepsSnapshot | null` — maps the persisted
  snake_case object to camelCase; returns `null` for `[]`, null, or empty content.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/shared/lib/agentSteps.test.ts
import { describe, it, expect } from 'vitest';
import { toAgentStepsSnapshot } from './agentSteps';

describe('toAgentStepsSnapshot', () => {
  it('returns null for empty/array/nullish inputs', () => {
    expect(toAgentStepsSnapshot(null)).toBeNull();
    expect(toAgentStepsSnapshot([])).toBeNull();
    expect(toAgentStepsSnapshot(undefined)).toBeNull();
    expect(toAgentStepsSnapshot({ steps: [], agencies: [], errors: [] })).toBeNull();
  });

  it('maps snake_case persisted shape to camelCase', () => {
    const snap = toAgentStepsSnapshot({
      steps: [{ name: 'discover', ms: 1200 }],
      agencies: [{ id: 'land', name: 'กรมที่ดิน', status: 'passed',
                   error_type: null, relevance_score: 0.9, section_label: 'fees' }],
      errors: [{ agency: 'x', name: 'X', error_type: 'timeout', message: 'm' }],
    })!;
    expect(snap.steps).toEqual([{ name: 'discover', ms: 1200 }]);
    expect(snap.agencies[0]).toEqual({
      id: 'land', name: 'กรมที่ดิน', status: 'passed',
      errorType: null, relevanceScore: 0.9, sectionLabel: 'fees',
    });
    expect(snap.errors[0]).toEqual({ agency: 'x', name: 'X', errorType: 'timeout', message: 'm' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && rtk vitest run src/shared/lib/agentSteps.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/shared/lib/agentSteps.ts
import type { AgentStepsSnapshot } from '@/shared/types/chat';

/**
 * Normalize a persisted `agent_steps` value (snake_case object, or the legacy
 * `[]` default) into an AgentStepsSnapshot. Returns null when there is nothing
 * worth showing, so callers can conditionally render the card.
 */
export function toAgentStepsSnapshot(raw: unknown): AgentStepsSnapshot | null {
  if (!raw || Array.isArray(raw) || typeof raw !== 'object') return null;
  const obj = raw as Record<string, any>;
  const steps = (obj.steps ?? []).map((s: any) => ({ name: s.name, ms: s.ms ?? null }));
  const agencies = (obj.agencies ?? []).map((a: any) => ({
    id: a.id, name: a.name ?? null, status: a.status,
    errorType: a.error_type ?? null, relevanceScore: a.relevance_score ?? null,
    sectionLabel: a.section_label ?? null,
  }));
  const errors = (obj.errors ?? []).map((e: any) => ({
    agency: e.agency ?? '', name: e.name ?? '',
    errorType: e.error_type ?? '', message: e.message ?? '',
  }));
  if (!steps.length && !agencies.length && !errors.length) return null;
  return { steps, agencies, errors };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && rtk vitest run src/shared/lib/agentSteps.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/shared/lib/agentSteps.ts frontend/src/shared/lib/agentSteps.test.ts
rtk git commit -m "feat(chat): normalizer for persisted agent-step snapshots"
```

---

## Task 6: Frontend — `AgentStepsCard` component

**Files:**
- Create: `frontend/src/shared/components/AgentStepsCard.tsx`
- Test: `frontend/src/shared/components/AgentStepsCard.test.tsx`

**Interfaces:**
- Consumes: `AgentStepsSnapshot` (Task 4).
- Produces: `AgentStepsCard({ steps }: { steps: AgentStepsSnapshot | null })` — a collapsible card,
  collapsed by default; renders nothing when `steps` is null.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/shared/components/AgentStepsCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AgentStepsCard } from './AgentStepsCard';

const snap = {
  steps: [{ name: 'discover', ms: 1200 }],
  agencies: [{ id: 'land', name: 'กรมที่ดิน', status: 'passed' as const }],
  errors: [],
};

describe('AgentStepsCard', () => {
  it('renders nothing when steps is null', () => {
    const { container } = render(<AgentStepsCard steps={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('is collapsed by default and expands on click', () => {
    render(<AgentStepsCard steps={snap} />);
    expect(screen.queryByText('กรมที่ดิน')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('กรมที่ดิน')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && rtk vitest run src/shared/components/AgentStepsCard.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/shared/components/AgentStepsCard.tsx
import { useState } from 'react';
import { Activity, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/shared/lib/utils';
import type { AgentStepsSnapshot } from '@/shared/types/chat';

const STEP_LABELS: Record<string, { icon: string; label: string }> = {
  discover: { icon: '🔍', label: 'ค้นหาหน่วยงาน' },
  classify: { icon: '🧠', label: 'วิเคราะห์คำถาม' },
  invoke: { icon: '🔗', label: 'สืบค้นจากหน่วยงาน' },
  verify: { icon: '✅', label: 'ตรวจสอบความเกี่ยวข้อง' },
  summarize: { icon: '📌', label: 'สรุปภาพรวม' },
  synthesize: { icon: '📝', label: 'สังเคราะห์คำตอบ' },
};

const AGENCY_ICON: Record<string, string> = {
  error: '❌', passed: '✅', rejected: '⚠️', ok: '⏳', running: '🔗', pending: '🔗',
};

export function AgentStepsCard({ steps }: { steps: AgentStepsSnapshot | null }) {
  const [open, setOpen] = useState(false);
  if (!steps) return null;

  return (
    <div className="rounded-lg border border-border bg-muted/40 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <Activity className="h-3.5 w-3.5 shrink-0" />
        <span className="font-medium">กระบวนการทำงานของ AI Agent</span>
        {open ? <ChevronUp className="ml-auto h-3.5 w-3.5" /> : <ChevronDown className="ml-auto h-3.5 w-3.5" />}
      </button>
      {open && (
        <div className="space-y-1.5 border-t border-border px-3 pb-3 pt-2 text-xs text-muted-foreground">
          {steps.steps.map((s, i) => {
            const info = STEP_LABELS[s.name] ?? { icon: '⚙️', label: s.name };
            return (
              <div key={`step-${i}`} className="flex items-center gap-2">
                <span>{info.icon}</span>
                <span className="text-foreground">{info.label}</span>
                {s.ms != null && <span className="text-[10px]">{(s.ms / 1000).toFixed(1)}s</span>}
                <span className="text-green-600 text-[10px]">✓</span>
              </div>
            );
          })}
          {steps.agencies.length > 0 && (
            <div className="ml-4 mt-1 space-y-1 border-l-2 border-muted pl-3">
              {steps.agencies.map((a) => (
                <div key={a.id} className="flex items-center gap-2">
                  <span>{AGENCY_ICON[a.status] ?? '🔗'}</span>
                  <span>{a.name ?? a.id}</span>
                  {a.errorType && <span className="text-destructive text-[10px]">({a.errorType})</span>}
                </div>
              ))}
            </div>
          )}
          {steps.errors.map((e, i) => (
            <div key={`err-${i}`} className={cn('flex items-center gap-2 text-destructive')}>
              <span>❌</span>
              <span>{e.name || e.errorType}: {e.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && rtk vitest run src/shared/components/AgentStepsCard.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/shared/components/AgentStepsCard.tsx frontend/src/shared/components/AgentStepsCard.test.tsx
rtk git commit -m "feat(chat): shared AgentStepsCard for persisted pipeline snapshot"
```

---

## Task 7: Frontend — wire the card into both message renderers

**Files:**
- Modify: `frontend/src/shared/components/AssistantMessageContent.tsx`
- Modify: `frontend/src/features/chat/MessageBubble.tsx`
- Modify: `frontend/src/features/history/MessageItem.tsx`
- Test: `frontend/src/shared/components/AssistantMessageContent.test.tsx` (add cases)

**Interfaces:**
- Consumes: `AgentStepsCard` (Task 6), `AgentStepsSnapshot` (Task 4), `toAgentStepsSnapshot` (Task 5),
  `ChatMessage.pipeline` (Task 4).
- Produces: `AssistantMessageContent` accepts `steps?: AgentStepsSnapshot | null` and renders the
  card after the summary.

- [ ] **Step 1: Write the failing test** (append to `AssistantMessageContent.test.tsx`)

```tsx
import { fireEvent } from '@testing-library/react';

describe('AssistantMessageContent agent steps', () => {
  it('renders the agent-steps card when steps are present', () => {
    render(
      <AssistantMessageContent
        content="คำตอบ"
        steps={{ steps: [{ name: 'discover', ms: 1000 }], agencies: [], errors: [] }}
      />,
    );
    expect(screen.getByText('กระบวนการทำงานของ AI Agent')).toBeInTheDocument();
  });

  it('renders no agent-steps card when steps is null', () => {
    render(<AssistantMessageContent content="คำตอบ" steps={null} />);
    expect(screen.queryByText('กระบวนการทำงานของ AI Agent')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && rtk vitest run src/shared/components/AssistantMessageContent.test.tsx`
Expected: FAIL — `steps` prop is not accepted / card not rendered.

- [ ] **Step 3: Write minimal implementation**

In `AssistantMessageContent.tsx`, add imports and the prop, and render the card after `SummaryCard`:
```tsx
import { AgentStepsCard } from "@/shared/components/AgentStepsCard";
import type { AgentStepsSnapshot, SummaryReference } from "@/shared/types/chat";
```
```tsx
export function AssistantMessageContent({
  content,
  summary,
  references,
  steps,
}: {
  content: string;
  summary?: string | null;
  references?: SummaryReference[];
  steps?: AgentStepsSnapshot | null;
}) {
```
```tsx
      <SummaryCard summary={summary} references={references} />
      <AgentStepsCard steps={steps ?? null} />
    </>
```
In `MessageBubble.tsx`, pass the live snapshot:
```tsx
          <AssistantMessageContent
            content={message.content}
            summary={message.summary}
            references={message.summaryReferences}
            steps={message.pipeline}
          />
```
In `MessageItem.tsx`, add the import and pass the normalized persisted snapshot:
```tsx
import { toAgentStepsSnapshot } from "@/shared/lib/agentSteps";
```
```tsx
          <AssistantMessageContent
            content={msg.content}
            summary={msg.summary}
            references={msg.summary_references}
            steps={toAgentStepsSnapshot(msg.agent_steps)}
          />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && rtk vitest run src/shared/components/AssistantMessageContent.test.tsx`
Expected: PASS.

- [ ] **Step 5: Typecheck and run the full frontend suite**

Run: `cd frontend && rtk tsc --noEmit && rtk vitest run`
Expected: no type errors; all tests pass.

- [ ] **Step 6: Commit**

```bash
rtk git add frontend/src/shared/components/AssistantMessageContent.tsx frontend/src/shared/components/AssistantMessageContent.test.tsx frontend/src/features/chat/MessageBubble.tsx frontend/src/features/history/MessageItem.tsx
rtk git commit -m "feat(chat): show agent-steps card in chat and history"
```

---

## Task 8: Update context.md and finalize

**Files:**
- Modify: `context.md`

- [ ] **Step 1: Add a context.md entry** describing the persisted `agent_steps` snapshot: backend
  `build_pipeline_snapshot` folds streamed `step`/`agency_*` events into `Message.agent_steps` on
  `/chat/stream`; frontend `AgentStepsCard` (fed by `ChatMessage.pipeline` live or
  `toAgentStepsSnapshot(agent_steps)` in history) renders it collapsed after the summary in
  `AssistantMessageContent`. Reference the spec and plan paths.

- [ ] **Step 2: Run both suites once more**

Run: `cd backend && rtk pytest -q` and `cd frontend && rtk vitest run`
Expected: both green.

- [ ] **Step 3: Commit**

```bash
rtk git add context.md
rtk git commit -m "docs: record persisted agent-steps feature in context.md"
```

---

## Self-Review

**Spec coverage:**
- Persist snapshot in `agent_steps` (no migration) → Tasks 1–3.
- Full snapshot (steps + agencies + errors), errors inside → Task 1 (`build_pipeline_snapshot`), Task 5/6 render errors.
- `/chat/stream` only; cached replays empty; Responses API untouched → Task 3.
- Frontend `AgentStepsSnapshot` type + `ChatMessage` carrier → Task 4.
- Normalizer → Task 5. Static collapsible card, collapsed by default → Task 6.
- Card after summary, shared by both renderers → Task 7. Live-attach on done → Task 4 (`buildAiMessageFromState` sets `pipeline`).
- Tests both stacks → every task is TDD.

**Placeholder scan:** none — every code step has concrete content.

**Type consistency:** `AgentStepsSnapshot` (camelCase) defined in Task 4, consumed identically in Tasks 5–7; `build_pipeline_snapshot(events, errors)` signature identical in Tasks 1 and 3; `save_turn(agent_steps=...)` identical in Tasks 2 and 3; `toAgentStepsSnapshot` identical in Tasks 5 and 7. `ChatMessage.pipeline` set in Task 4, read in Task 7.

**Note (deviation from spec wording):** the spec said "retype `ChatMessage.agentSteps`." The plan instead adds a **new** `ChatMessage.pipeline` field and leaves the legacy `agentSteps: AgentStep[]` untouched, because `agentSteps` has several legacy consumers (mockData, historyApi, existing tests) that a retype would break. Backend still reuses the `agent_steps` column as approved; the frontend field name is the only change.
