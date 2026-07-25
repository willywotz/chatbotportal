# Responses API OneChat Version Selection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the OpenAI-compatible Responses API reach every OneChat upstream (v1–v5) on both HTTP and WebSocket, selected per-request, behind a single `onechat` model id.

**Architecture:** Version selection moves out of the Responses layer into one `resolve_version()` resolver in the OneChat client module (per-request override → newest). The client gains a uniform `events()` method that streams v4/v5 SSE and adapts the v1/v2/v3 single-JSON envelope into `answer`+`done` events, so one `ResponseAccumulator` drives all versions on all transports. The `CHAT_STREAM_VERSION` setting is removed.

**Tech Stack:** Python 3.12, FastAPI, httpx, Tortoise ORM, pytest (async). Backend lives in `backend/`; run tests from there.

## Global Constraints

- **TDD, mandatory:** failing test → confirm red → minimal code → confirm green → refactor. One assertion of behavior per test.
- **Run tests from `backend/`:** `cd backend && rtk pytest <path> -v`.
- **Style:** Google Python style; American English; organized imports; minimal comments (only non-obvious rationale).
- **Version vocabulary:** one declarative table `_STREAMS_SSE = {"v1": False, "v2": False, "v3": False, "v4": True, "v5": True}` is the single source of truth for the roster and each version's transport; `_VALID_VERSIONS = frozenset(_STREAMS_SSE)`; `NEWEST_VERSION = "v5"`. Never inline a `("v4","v5")` literal — consult the table.
- **Model id:** the only accepted public model id is `"onechat"` (hard rename — old `thai-citizen-guide*` ids are gone).
- **Per-request override channel:** request-body field `onechat_version` only (never a header — WebSocket can't set them).
- **Commit prefix:** conventional commits; end commit messages with the `Co-Authored-By` trailer per repo policy.

---

### Task 1: OneChat client — version resolver + uniform `events()`

**Files:**
- Modify: `backend/app/services/onechat/client.py`
- Test: `backend/tests/services/onechat/test_client_version.py` (create)

**Interfaces:**
- Consumes: existing `OneChatClient._stream`, `OneChatClient._post_json`, `settings`.
- Produces:
  - `resolve_version(requested: str | None = None) -> str`
  - `OneChatClient(base_url=None, *, transport=None, version: str | None = None)` with attribute `self.version: str`
  - `OneChatClient.events(query, mcp_endpoint_url, session_id=None) -> AsyncIterator[tuple[str, dict]]`
  - `get_client(version: str | None = None) -> OneChatClient`
  - `NEWEST_VERSION = "v5"`
  - (still present this task, removed in Task 2) `stream_by_version`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/onechat/test_client_version.py
import httpx
import pytest

from app.services.onechat.client import (
    NEWEST_VERSION, OneChatClient, get_client, resolve_version,
)


def test_resolve_version_uses_valid_override():
    assert resolve_version("v3") == "v3"
    assert resolve_version(" V4 ") == "v4"


def test_resolve_version_defaults_to_newest():
    assert resolve_version(None) == NEWEST_VERSION
    assert resolve_version("") == NEWEST_VERSION
    assert resolve_version("bogus") == NEWEST_VERSION


def test_client_pins_version_from_constructor():
    assert OneChatClient("http://oc:8000", version="v3").version == "v3"


def test_client_defaults_version_to_newest():
    assert OneChatClient("http://oc:8000").version == NEWEST_VERSION


def _sync_transport(payload: dict, rec: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if rec is not None:
            rec["url"] = str(request.url)
        return httpx.Response(200, json=payload)
    return httpx.MockTransport(handler)


async def test_events_v3_unwraps_data_into_answer_and_done():
    rec: dict = {}
    payload = {"data": {"answer": "hi", "sections": [],
                        "session_id": "s1", "debug": {"responseTimeMs": 1234}}}
    client = OneChatClient("http://oc:8000", transport=_sync_transport(payload, rec), version="v3")
    events = [ev async for ev in client.events("q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v3/chat"
    assert events[0] == ("answer", payload["data"])
    assert events[1] == ("done", {"session_id": "s1", "total_ms": 1234})


async def test_events_sync_tolerates_missing_data_envelope_and_debug():
    payload = {"answer": "hi", "session_id": "s1"}   # no "data", no "debug"
    client = OneChatClient("http://oc:8000", transport=_sync_transport(payload), version="v2")
    events = [ev async for ev in client.events("q", "http://mcp", None)]
    assert events[0] == ("answer", payload)
    assert events[1] == ("done", {"session_id": "s1", "total_ms": None})


async def test_events_v5_streams_sse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://oc:8000/v5/chat"
        body = 'event: answer\ndata: {"answer": "hi"}\n\nevent: done\ndata: {"session_id": "s1"}\n\n'
        return httpx.Response(200, text=body)
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler), version="v5")
    events = [ev async for ev in client.events("q", "http://mcp", "c")]
    assert ("answer", {"answer": "hi"}) in events
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && rtk pytest tests/services/onechat/test_client_version.py -v`
Expected: FAIL — `resolve_version` / `events` / `get_client(version=...)` not defined.

- [ ] **Step 3: Implement in `client.py`**

Add near the top (after `logger`):

```python
# OneChat upstreams: version → does its /chat endpoint stream SSE?
# v1-v3 return a single JSON envelope; v4-v5 stream. A fact about the service
# (spec/api/), not something the version string implies.
_STREAMS_SSE = {"v1": False, "v2": False, "v3": False, "v4": True, "v5": True}
_VALID_VERSIONS = frozenset(_STREAMS_SSE)
NEWEST_VERSION = "v5"                 # explicit: "newest" is editorial, not max()


def resolve_version(requested: str | None = None) -> str:
    """Per-request override wins; anything invalid/absent → newest."""
    v = (requested or "").strip().lower()
    return v if v in _VALID_VERSIONS else NEWEST_VERSION
```

Extend `OneChatClient.__init__` to accept and store a version:

```python
    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        version: str | None = None,
    ):
        self._base_url = (base_url or settings.ONECHAT_BASE_URL).rstrip("/")
        self._transport = transport
        self.version = version or NEWEST_VERSION
```

Add `events()` (keep `stream_by_version` for now; removed in Task 2):

```python
    async def events(
        self, query: str, mcp_endpoint_url: str, session_id: str | None = None
    ) -> AsyncIterator[SseEvent]:
        """Uniform event stream for this client's pinned version.

        v4/v5 stream SSE; v1/v2/v3 return one JSON envelope, adapted into a
        single `answer` event plus a terminal `done` (spec/api/v3.md: v3 `data`
        equals the streaming `answer` payload).
        """
        v = self.version
        if _STREAMS_SSE[v]:
            async for ev in self._stream(f"/{v}/chat", query, mcp_endpoint_url, session_id):
                yield ev
            return
        envelope = await self._post_json(f"/{v}/chat", query, mcp_endpoint_url, session_id)
        data = envelope.get("data", envelope)
        yield ("answer", data)
        yield ("done", {
            "session_id": data.get("session_id"),
            "total_ms": (data.get("debug") or {}).get("responseTimeMs"),
        })
```

Update `get_client` at the bottom of the file:

```python
def get_client(version: str | None = None) -> OneChatClient:
    return OneChatClient(version=version or resolve_version())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && rtk pytest tests/services/onechat/test_client_version.py -v`
Expected: PASS (all 7).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/onechat/client.py backend/tests/services/onechat/test_client_version.py
rtk git commit -m "feat(onechat): add resolve_version and uniform events() for v1-v5"
```

---

### Task 2: Migrate the turn pipeline to `events()`; retire `stream_by_version`

**Files:**
- Modify: `backend/app/services/chat/stream.py:64-71` (`_stream_version`), `:74-88` (`prepare_turn`), `:151-156` (`_stream_live` call site)
- Modify: `backend/app/services/onechat/client.py` (delete `stream_by_version`, lines ~117-125)
- Test: `backend/tests/routers/test_chat_stream_upstream.py:145-149` (rewrite), `backend/tests/services/onechat/test_client_stream.py:42-53` (replace two `stream_by_version` tests)

**Interfaces:**
- Consumes: `resolve_version`, `get_client` (Task 1); `TurnPlan.stream_version`.
- Produces: `prepare_turn(*, query, conversation_id, user, is_continuation, requested_version: str | None = None) -> TurnPlan`; `_stream_version()` now returns `resolve_version()`.

- [ ] **Step 1: Rewrite the failing tests**

Replace `test_stream_version_resolves_without_url` in `test_chat_stream_upstream.py`:

```python
def test_stream_version_uses_resolver_default():
    from app.services.chat import stream as turn_stream
    assert turn_stream._stream_version() == "v5"
```

Replace the two `stream_by_version` tests in `test_client_stream.py` (lines 42-53) with:

```python
async def test_events_selects_v4_stream():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_v4v5_transport(rec), version="v4")
    _ = [ev async for ev in client.events("q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v4/chat"
```

(Reuse whatever SSE transport helper the file already defines for v4/v5; name it to match — inspect the top of `test_client_stream.py` first.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && rtk pytest tests/routers/test_chat_stream_upstream.py::test_stream_version_uses_resolver_default tests/services/onechat/test_client_stream.py -v`
Expected: FAIL — `events` on `v4` not yet wired via the caller / `stream_by_version` still referenced.

- [ ] **Step 3: Update `chat/stream.py`**

Replace `_stream_version` (imports `resolve_version` from the client):

```python
from app.services.onechat import OneChatError, get_client, resolve_version


def _stream_version() -> str:
    """Streaming version resolver (kept for the chat.py re-export)."""
    return resolve_version()
```

Add the `requested_version` parameter to `prepare_turn` and use it:

```python
async def prepare_turn(
    *, query: str, conversation_id: str, user: User | None, is_continuation: bool,
    requested_version: str | None = None,
) -> TurnPlan:
    ...
    stream_version = resolve_version(requested_version)
    plan = TurnPlan(
        query=query, conversation_id=conversation_id, user=user,
        stream_version=stream_version, assistant_message_id=generate_uuid(),
    )
    ...
```

Update `_stream_live`'s upstream call:

```python
    async for event_name, event_data in get_client(version).events(
        plan.query, settings.MCP_ENDPOINT_URL, plan.conversation_id
    ):
```

(`version = plan.stream_version` is already assigned at the top of `_stream_live`.)

- [ ] **Step 4: Delete `stream_by_version` from `client.py`**

Remove the `stream_by_version` method (lines ~117-125). `events()` replaces it.

- [ ] **Step 5: Run the affected suites**

Run: `cd backend && rtk pytest tests/routers/test_chat_stream_upstream.py tests/services/onechat/ tests/services/test_chat_turn_stream.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/services/chat/stream.py backend/app/services/onechat/client.py backend/tests/routers/test_chat_stream_upstream.py backend/tests/services/onechat/test_client_stream.py
rtk git commit -m "refactor(chat): drive turns through OneChat events(); remove stream_by_version"
```

---

### Task 3: Rename model id to `onechat`; add `onechat_version`; simplify `resolve_model`

**Files:**
- Modify: `backend/app/services/responses/request.py` (`DEFAULT_MODEL_ID`, `MODEL_IDS`→gone, `resolve_model`)
- Modify: `backend/app/schemas/responses.py:15` (default), add `onechat_version`
- Modify: `backend/app/services/responses/retrieve.py:35` (echo id)
- Test: `backend/tests/services/test_responses_request.py` (rewrite the model tests)

**Interfaces:**
- Consumes: `ResponsesApiError`.
- Produces: `DEFAULT_MODEL_ID = "onechat"`; `resolve_model(model: str) -> str` (no version tuple); `ResponsesRequest.onechat_version: str | None`.

- [ ] **Step 1: Rewrite the failing tests**

Replace the version fixture + first three tests in `test_responses_request.py` with:

```python
def test_resolve_model_accepts_onechat():
    assert resolve_model("onechat") == "onechat"


def test_resolve_model_rejects_old_thai_citizen_guide_ids():
    for old in ("thai-citizen-guide", "thai-citizen-guide-v5", "thai-citizen-guide-v4"):
        with pytest.raises(ResponsesApiError) as exc:
            resolve_model(old)
        assert exc.value.status == 400
        assert exc.value.param == "model"


def test_resolve_model_rejects_unknown_model():
    with pytest.raises(ResponsesApiError) as exc:
        resolve_model("gpt-5")
    assert exc.value.param == "model"


def test_onechat_version_defaults_to_none():
    req = ResponsesRequest.model_validate({"model": "onechat", "input": "hi"})
    assert req.onechat_version is None


def test_onechat_version_is_accepted():
    req = ResponsesRequest.model_validate(
        {"model": "onechat", "input": "hi", "onechat_version": "v3"})
    assert req.onechat_version == "v3"
```

Delete the `restore_version` fixture and update the remaining `model="thai-citizen-guide"` literals in this file (the `extract_query`, `unsupported_fields`, `store_and_generate` tests) to `"onechat"`. Remove the now-unused `from app.config import settings` import if nothing else uses it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && rtk pytest tests/services/test_responses_request.py -v`
Expected: FAIL — `resolve_model` returns a tuple / `onechat_version` unknown.

- [ ] **Step 3: Rewrite `request.py`**

```python
"""Translate an OpenAI Responses request into portal turn parameters."""
from typing import Any

from app.services.responses.errors import ResponsesApiError

DEFAULT_MODEL_ID = "onechat"


def resolve_model(model: str) -> str:
    """Validate the public model id. Version is chosen elsewhere, per request."""
    if model != DEFAULT_MODEL_ID:
        raise ResponsesApiError(
            f"Unknown model '{model}'. Supported model: {DEFAULT_MODEL_ID}.",
            param="model",
        )
    return model
```

(Leave `extract_query` unchanged below.)

- [ ] **Step 4: Update the schema**

In `schemas/responses.py`:

```python
    model: str = "onechat"
    input: str | list[dict[str, Any]] = ""
    previous_response_id: str | None = None
    conversation: str | None = None
    stream: bool = False
    store: bool = True
    generate: bool = True
    # OneChat upstream override (v1..v5); invalid/absent → newest. Body field so
    # it works on WebSocket, which cannot set headers.
    onechat_version: str | None = None
```

- [ ] **Step 5: Update the retrieve echo**

`retrieve.py:35`: change `"model": "thai-citizen-guide",` to `"model": "onechat",`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && rtk pytest tests/services/test_responses_request.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
rtk git add backend/app/services/responses/request.py backend/app/schemas/responses.py backend/app/services/responses/retrieve.py backend/tests/services/test_responses_request.py
rtk git commit -m "feat(responses): rename model id to onechat, add onechat_version override"
```

---

### Task 4: Thread `onechat_version` through the router; rename model literals in Responses tests

**Files:**
- Modify: `backend/app/routers/responses.py:54` and `:73-75` (`run_response`)
- Test: `backend/tests/routers/test_responses_http.py`, `backend/tests/routers/test_responses_ws_route.py`, `backend/tests/routers/test_responses_stubs.py`, `backend/tests/services/test_responses_translate.py`, `backend/tests/services/test_responses_ws_session.py` (rename literals + add override e2e)

**Interfaces:**
- Consumes: `resolve_model` (now returns a str), `prepare_turn(requested_version=...)`.
- Produces: no new symbols; `run_response` honours `request.onechat_version`.

- [ ] **Step 1: Write the failing override tests**

Add to `test_responses_http.py` (mirror an existing streaming test's upstream stub, asserting the upstream path is `/v3/chat`):

```python
async def test_http_onechat_version_routes_to_v3(...):
    request = ResponsesRequest(model="onechat", input="บัตรหาย", onechat_version="v3")
    # stub OneChat so a POST to /v3/chat returns {"data": {"answer": "ok", "session_id": "s1"}}
    # drive run_response and assert a response.completed with output_text "ok"
```

Add the WebSocket analogue to `test_responses_ws_route.py`:

```python
# a response.create frame with {"model": "onechat", "onechat_version": "v3", "input": "บัตรหาย"}
# asserts the upstream hit /v3/chat and a response.completed frame comes back
```

(Match each file's existing OneChat stubbing style — inspect a neighbouring test in the same file first; reuse its fixtures.)

- [ ] **Step 2: Rename literals**

Across the five test files, replace every `"thai-citizen-guide"` / `"thai-citizen-guide-v5"` / `"thai-citizen-guide-v4"` model literal with `"onechat"`. In `test_responses_translate.py`, the `ResponseAccumulator(model=...)` echo assertions become `"onechat"`.

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `cd backend && rtk pytest tests/routers/test_responses_http.py tests/routers/test_responses_ws_route.py -v`
Expected: FAIL — override not wired (upstream still hits v5).

- [ ] **Step 4: Wire the router**

In `run_response` (`responses.py`):

```python
    model = resolve_model(request.model)
    query = extract_query(request.input)
    conversation_id, is_continuation = await resolve_conversation(...)
    try:
        plan = await prepare_turn(
            query=query, conversation_id=conversation_id, user=user,
            is_continuation=is_continuation, requested_version=request.onechat_version,
        )
    except ConversationNotFound:
        ...
```

Delete the reconciliation block (old lines 73-75):

```python
    # A model id that pins a version wins over CHAT_STREAM_VERSION.
    if plan.stream_version != stream_version:
        plan.stream_version = stream_version
```

`accumulator = ResponseAccumulator(..., model=model, ..., stream_version=plan.stream_version)` stays; `model` is now a plain str.

- [ ] **Step 5: Run the Responses suites**

Run: `cd backend && rtk pytest tests/routers/test_responses_http.py tests/routers/test_responses_ws_route.py tests/routers/test_responses_stubs.py tests/services/test_responses_translate.py tests/services/test_responses_ws_session.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/routers/responses.py backend/tests/routers/test_responses_http.py backend/tests/routers/test_responses_ws_route.py backend/tests/routers/test_responses_stubs.py backend/tests/services/test_responses_translate.py backend/tests/services/test_responses_ws_session.py
rtk git commit -m "feat(responses): honour per-request onechat_version on HTTP and WS"
```

---

### Task 5: Remove `CHAT_STREAM_VERSION`

**Files:**
- Modify: `backend/app/config.py:69` (delete setting), `:154` (`SETTINGS_GROUPS["OneChat"]`)
- Modify: `.env.prod.example:31` (delete line)
- Modify: `backend/tests/test_config_onechat_base.py:16-18`
- Delete: `backend/tests/routers/test_chat_stream_version.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `SETTINGS_GROUPS["OneChat"] == ["MCP_ENDPOINT_URL", "ONECHAT_BASE_URL"]`.

- [ ] **Step 1: Update the failing config test**

In `test_config_onechat_base.py`, change the `test_legacy_onechat_urls_removed` expectation:

```python
    assert config.SETTINGS_GROUPS["OneChat"] == [
        "MCP_ENDPOINT_URL", "ONECHAT_BASE_URL",
    ]
```

Add:

```python
def test_chat_stream_version_setting_removed():
    from app import config
    assert not hasattr(config.settings, "CHAT_STREAM_VERSION")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && rtk pytest tests/test_config_onechat_base.py -v`
Expected: FAIL — setting still present / group still lists it.

- [ ] **Step 3: Delete the setting and group entry**

`config.py`: remove the `CHAT_STREAM_VERSION: str = "v5" ...` line; change the group to
`"OneChat": ["MCP_ENDPOINT_URL", "ONECHAT_BASE_URL"],`.

`.env.prod.example`: delete the `CHAT_STREAM_VERSION=v5` line.

- [ ] **Step 4: Delete the obsolete test file**

```bash
rtk git rm backend/tests/routers/test_chat_stream_version.py
```

(Its premise — the setting — no longer exists. `_stream_version()` is covered by Task 2's resolver test.)

- [ ] **Step 5: Run config + a broad smoke**

Run: `cd backend && rtk pytest tests/test_config_onechat_base.py tests/routers/test_chat_stream_upstream.py -v`
Expected: PASS.

- [ ] **Step 6: Confirm no references remain**

Run: `git grep -n CHAT_STREAM_VERSION -- backend/app '.env.prod.example'`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
rtk git add backend/app/config.py .env.prod.example backend/tests/test_config_onechat_base.py
rtk git commit -m "chore(config): remove CHAT_STREAM_VERSION; version is per-request now"
```

---

### Task 6: Full suite, living docs, context.md

**Files:**
- Modify: `spec/openai-responses.md:85`, `spec/openai-responses-spec-gap-log.md:71-73`
- Modify: `context.md`
- (No `docs/superpowers/plans/*` historical edits.)

**Interfaces:** none (documentation).

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && rtk pytest -q`
Expected: PASS (0 failures). Fix any stray `thai-citizen-guide` / `CHAT_STREAM_VERSION` references surfaced.

- [ ] **Step 2: Update the living spec**

In `spec/openai-responses.md`, replace the model table row:

```
| `onechat` | Follows `onechat_version` (v1–v5); absent/invalid → newest (v5) |
```

In `spec/openai-responses-spec-gap-log.md`, replace the two `CHAT_STREAM_VERSION` rows with one noting version now comes from the `onechat_version` request field (absent → newest), and drop the "pinned model overrides" row.

- [ ] **Step 3: Update `context.md`**

Update the OneChat/Responses section to state: single `onechat` model id; per-request `onechat_version` (v1–v5, else newest); `CHAT_STREAM_VERSION` removed; portal `/chat/stream` now always newest. Follow the file's existing structure.

- [ ] **Step 4: Commit**

```bash
rtk git add spec/openai-responses.md spec/openai-responses-spec-gap-log.md context.md
rtk git commit -m "docs: document onechat model id and per-request version selection"
```

---

## Self-Review

**Spec coverage:**
- §2 resolver → Task 1. §3 model id → Task 3. §4 override field → Task 3 (schema) + Task 4 (routing). §5 `events()` v1/v2/v3 → Task 1. §6 flow/portal → Task 2 + Task 4. §7 remove setting → Task 5. §8 blast radius → Tasks 3–6. §9 acceptance → Task 6 full suite + the e2e tests in Task 4.

**Type consistency:** `resolve_version(requested)->str`, `resolve_model(model)->str` (Task 3/4 both treat the return as a plain str, matching), `events(query, mcp, session_id)`, `get_client(version)`, `prepare_turn(..., requested_version=None)` (defined Task 2, called Task 4), `NEWEST_VERSION` used in Tasks 1–2. Consistent across tasks.

**Placeholder scan:** test stubs in Task 4 intentionally say "match the neighbouring file's fixture" because each Responses test file wires its OneChat stub differently; the implementer must inspect the sibling test — this is guidance, not a missing implementation (the assertions and routing are fully specified).
