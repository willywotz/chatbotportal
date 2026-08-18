# Lean Backend — Dead-Code Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the dead OneChat stream methods and the whole unused OpenAI-compatible API surface, and keep the backend test suite green.

**Architecture:** Deletion, not construction. Deleting code is TDD-inverted: the "test" is the existing suite, which must stay green after removal. Where a live behavior was only covered by a test that also touched dead code, we re-point that test at the live path so we lose no coverage. Each task ends with a green suite and a grep proof that the code is gone.

**Tech Stack:** Python 3, uv, pytest + pytest-asyncio, Tortoise ORM, FastAPI (delivery only), Caddy (reverse proxy).

**Spec:** `docs/superpowers/specs/2026-08-18-lean-decouple-backend-design.md` (Part A). This plan implements Part A only (Lean, phases L0 + L1). Part B (de-couple, phases D1–D3) is planned separately after L1 lands, because its targets shift once this deletion completes.

## Global Constraints

- Test command (full suite): `cd backend && uv run pytest`
- Test command (one test): `cd backend && uv run pytest <path>::<name> -v`
- One branch per phase (project rule): `chore/dead-onechat-stream` for Task 1, `refactor/remove-openai-surface` for Task 2.
- TDD is mandatory; for deletion this means "suite green before → change → suite green after", plus a grep proof.
- After the work: update `CONTEXT.md` and commit (project rule). The orchestrator does this, not the task.
- Docs prose: ASD-STE100 Simplified Technical English.
- The native `conversations.py` router (prefix `/history`) STAYS. Only `openai_conversations.py` and `responses.py` are deleted.

---

### Task 1: Delete dead OneChat `stream_v4` / `stream_v5`

**Branch:** `chore/dead-onechat-stream`

**Files:**
- Modify: `backend/app/services/onechat/client.py` (remove `stream_v4` at ~`:116-120` and `stream_v5` at ~`:122-126`)
- Modify: `backend/tests/services/onechat/test_client_stream.py` (drop the `stream_v5` reorder test; re-point two error tests at the live `events()` path)
- Modify: `backend/pyproject.toml:48` (fix stale `app.main:app` comment → `app.main:asgi_app`)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing other tasks rely on. `OneChatClient.events()` remains the sole streaming entry point (signature unchanged: `events(question, mcp_url, conversation_id)`).

- [ ] **Step 1: Record the green baseline**

Run: `cd backend && uv run pytest -q`
Expected: PASS. Write down the pass/skip counts (for example `849 passed, 2 skipped`). Later steps must not lose passes except the one test we intentionally delete.

- [ ] **Step 2: Confirm the methods are dead**

Run: `cd backend && grep -rn 'stream_v4\|stream_v5' app tests`
Expected: matches ONLY in `app/services/onechat/client.py` (the definitions) and `tests/services/onechat/test_client_stream.py`. No other caller anywhere. If any other file matches, STOP — the method is not dead; report it.

- [ ] **Step 3: Re-point the two error tests at the live path (write them first)**

Replace the whole body of `backend/tests/services/onechat/test_client_stream.py` with this. It keeps `parse_sse_block`, `events`, and both error-mapping tests, and deletes only the `stream_v5` reorder test. The two error tests now drive `events()` instead of the dead `stream_v5`.

```python
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


async def test_events_selects_v4_stream():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec), version="v4")
    _ = [ev async for ev in client.events("q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v4/chat"


async def test_stream_non_200_raises_onechat_error():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec, status=500))
    with pytest.raises(OneChatError) as exc:
        _ = [ev async for ev in client.events("q", "http://mcp", "c")]
    assert exc.value.status_code == 500


async def test_stream_read_timeout_maps_to_504():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    with pytest.raises(OneChatError) as exc:
        _ = [ev async for ev in client.events("q", "http://mcp", "c")]
    assert exc.value.status_code == 504
```

- [ ] **Step 4: Run the rewritten error tests — they must still PASS (they now use `events()`, which still exists)**

Run: `cd backend && uv run pytest tests/services/onechat/test_client_stream.py -v`
Expected: PASS for all four remaining tests. This proves the error-mapping coverage survives without `stream_v5`.

- [ ] **Step 5: Delete the dead methods**

In `backend/app/services/onechat/client.py`, delete the `stream_v4` method and the `stream_v5` method in full (the two thin wrappers around `self._stream(...)`, around lines 116-126). Leave `events()`, `_stream()`, and everything else untouched.

- [ ] **Step 6: Fix the stale comment**

In `backend/pyproject.toml:48`, change the comment reference `app.main:app` to `app.main:asgi_app`.

- [ ] **Step 7: Prove the methods are gone and the suite is green**

Run: `cd backend && grep -rn 'stream_v4\|stream_v5' app tests`
Expected: NO matches.

Run: `cd backend && uv run pytest -q`
Expected: PASS. Count = baseline minus exactly 1 (the deleted `test_stream_v5_yields_events_in_order`).

- [ ] **Step 8: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add backend/app/services/onechat/client.py backend/tests/services/onechat/test_client_stream.py backend/pyproject.toml
git commit -m "chore(onechat): remove dead stream_v4/stream_v5 wrappers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Delete the OpenAI-compatible API surface

**Branch:** `refactor/remove-openai-surface`

**Files:**
- Delete: `backend/app/routers/openai_conversations.py`
- Delete: `backend/app/routers/responses.py`
- Delete (whole dir): `backend/app/services/openai/` (`conversations.py`, `identity.py`, `ids.py`, `items.py`, `metadata.py`, `__init__.py`)
- Delete (whole dir): `backend/app/services/responses/` (`continuity.py`, `errors.py`, `request.py`, `retrieve.py`, `session.py`, `translate.py`, `__init__.py`)
- Modify: `backend/app/main.py` (remove imports `:48-49` and `include_router` lines `:145-146`)
- Modify: `backend/app/errors.py` (remove the `register_responses_error_handler` import + call, `:67-69`)
- Modify: `backend/app/config.py` (remove `RESPONSES_WS_MAX_CONNECTIONS` and `RESPONSES_WS_MAX_DURATION_SECONDS`, `:80-81`)
- Modify: `caddy/Caddyfile` (remove the `@api_responses` block + its comment, `:26-38`)
- Delete tests: `backend/tests/services/test_openai_conversations.py`, `test_openai_ids.py`, `test_openai_identity.py`, `test_openai_items.py`, `test_openai_metadata.py`, `backend/tests/services/test_responses_retrieve.py`, `test_responses_request.py`, `test_responses_translate.py`, `test_responses_ws_session.py`, `test_responses_continuity.py`, `backend/tests/routers/test_responses_http.py`, `backend/tests/routers/test_responses_ws_route.py`
- Modify (rewrite, do NOT delete): `backend/tests/services/test_soft_delete_filter.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: nothing. This task only removes routes; it drops no database table and changes no kept route.

**Note on atomicity:** the code and its tests must be removed together in one commit, or the suite goes red mid-way. Do the whole task, then run the suite once at the end.

- [ ] **Step 1: Record the green baseline (on the new branch, after Task 1 merged)**

Run: `cd backend && uv run pytest -q`
Expected: PASS. Record the counts.

- [ ] **Step 2: Rewrite the soft-delete test to drop the deleted `responses` dependency**

`backend/tests/services/test_soft_delete_filter.py` keeps only the native-path case and loses the two `responses.continuity` cases. Replace the whole file with:

```python
import pytest

from app.errors import ApiError
from app.models.conversation import Conversation
from app.models.user import User
from app.routers.conversations import get_conversation_messages
from app.utils import now


@pytest.mark.asyncio
async def test_get_messages_404s_for_soft_deleted_conversation(db):
    owner = await User.create(email="owner-soft-del@x.com", hashed_password="h", role="user")
    conv = await Conversation.create(
        title="t", status="active", user_id=owner.id, deleted_at=now()
    )
    with pytest.raises(ApiError) as exc:
        await get_conversation_messages(conv.id, owner)
    assert exc.value.status == 404
```

- [ ] **Step 3: Delete the two routers**

```bash
cd /home/foo/nectec/chatbotportal
git rm backend/app/routers/openai_conversations.py backend/app/routers/responses.py
```

- [ ] **Step 4: Delete the two service packages**

```bash
git rm -r backend/app/services/openai backend/app/services/responses
```

- [ ] **Step 5: Delete the obsolete test files**

```bash
git rm backend/tests/services/test_openai_conversations.py backend/tests/services/test_openai_ids.py backend/tests/services/test_openai_identity.py backend/tests/services/test_openai_items.py backend/tests/services/test_openai_metadata.py backend/tests/services/test_responses_retrieve.py backend/tests/services/test_responses_request.py backend/tests/services/test_responses_translate.py backend/tests/services/test_responses_ws_session.py backend/tests/services/test_responses_continuity.py backend/tests/routers/test_responses_http.py backend/tests/routers/test_responses_ws_route.py
```

- [ ] **Step 6: Remove the router wiring in `main.py`**

In `backend/app/main.py`:
- Delete line `:48` `from app.routers import openai_conversations`
- Delete line `:49` `from app.routers import responses`
- Delete line `:145` `app.include_router(responses.router, prefix="/api/v1")`
- Delete line `:146` `app.include_router(openai_conversations.router, prefix="/api/v1")`

- [ ] **Step 7: Remove the error-handler glue in `errors.py`**

In `backend/app/errors.py`, delete lines `:67-69`:

```python
    from app.services.responses.errors import register_responses_error_handler

    register_responses_error_handler(app)
```

- [ ] **Step 8: Remove the dead config fields**

In `backend/app/config.py`, delete lines `:80-81`:

```python
    RESPONSES_WS_MAX_CONNECTIONS: int = 1024
    RESPONSES_WS_MAX_DURATION_SECONDS: int = 900
```

- [ ] **Step 9: Remove the Caddy block**

In `caddy/Caddyfile`, delete lines `:26-38` — the comment block starting `# OpenAI Responses API.` through the closing `}` of `handle @api_responses { ... }`. Leave the general `@backend` block (`:40` onward) untouched. After removal, `/api/v1/responses` falls through to `@backend` and returns 404, which is correct.

- [ ] **Step 10: Prove nothing still references the deleted code**

Run: `cd backend && grep -rnE 'services\.(openai|responses)|routers\.(responses|openai_conversations)|run_response|register_responses_error_handler|RESPONSES_WS_' app`
Expected: NO matches.

Run: `cd backend && python -c "import app.main"`
Expected: no ImportError.

- [ ] **Step 11: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: PASS. Count = baseline minus the 12 deleted test files' tests, minus the 2 removed `responses.continuity` cases from `test_soft_delete_filter.py`. No FAIL, no ERROR (an ImportError from a missed reference shows here as a collection ERROR).

- [ ] **Step 12: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add -A
git commit -m "refactor: remove unused OpenAI-compatible API surface

Delete /responses and OpenAI /conversations routers and their
services/openai + services/responses packages. No internal or frontend
caller. Also removes the openai<->responses import cycle and the
router-import + FastAPI-in-service dependency-rule leaks for free.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Post-task (orchestrator, after both tasks pass)

- [ ] Update `CONTEXT.md` with a changelog entry for the deletion (STE), and commit it.
- [ ] Before merging Task 2 to a deployed environment, run the spec's deploy-time safety check: confirm no external ops client calls `/api/v1/responses` or `/api/v1/conversations` (check access logs). This is a deploy gate, not a code gate.

## Self-review notes

- **Spec coverage (Part A):** A0 trivial deletions → Task 1 (methods, test, comment). A1 OpenAI surface → Task 2 (routers, both service packages, 3 glue edits, Caddy, tests, soft-delete rewrite). A2 (`mcp/client.py`) is out of scope per the spec.
- **No lost coverage:** the two OneChat error-mapping tests are re-pointed at `events()`; the native soft-delete 404 case is kept.
- **Types/names consistent:** `events(question, mcp_url, conversation_id)` used the same way in every rewritten test; `get_conversation_messages(conv_id, owner)` and `ApiError.status` match the original file.
