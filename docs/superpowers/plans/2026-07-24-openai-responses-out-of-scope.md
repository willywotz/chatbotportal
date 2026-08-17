# OpenAI Responses Out-of-Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement every OpenAI Responses/Conversations endpoint the base spec marks "Out of scope" — real for Kind 1 (retrieve/delete/input_items + Conversations + items), `501` for Kind 2 (cancel/input_tokens/compact) — backed by the existing `Conversation`/`Message` store.

**Architecture:** A new OpenAI-shaped `conversations` router takes `/api/v1/conversations`; the native SPA history router relocates to `/api/v1/history`. New response sub-routes are added to the existing responses router. Anonymous callers get an ephemeral `User` + JWT returned via `X-Portal-Session`; every new endpoint enforces `owner == caller` and returns `404` (never `403`) on ownership failure. Deletes are soft (`deleted_at`), filtered from all reads.

**Tech Stack:** FastAPI, Tortoise ORM + aerich migrations, Pydantic v2, pytest (backend); React + MSW/vitest (frontend). Token-optimized shell via `rtk`.

## Global Constraints

- **TDD, no exceptions:** failing test → confirm fail → minimal code → confirm pass → refactor (CLAUDE.md).
- **Branching:** each phase is its own branch off `dev`: `feat/oai-foundation`, `feat/oai-conversations`, `feat/oai-responses-retrieve`. Never commit multi-task work to `main`/`dev` directly.
- **Style:** Google Python style; American English; organized imports; minimal comments (only non-obvious rationale).
- **Wire rules (from `spec/openai-responses.md` + `spec/openai-responses-extended.md`):** all JSON `ensure_ascii=False`; errors use `ResponsesApiError.envelope()` (`{error:{message,type,param,code}}`), never `app/errors.py`; ownership failure → `404` not `403`; id prefixes `resp_`/`conv_`/`msg_` accepted-and-stripped, always emitted; `usage` stays the zero object; the 9-event stream is unchanged (no new streaming events).
- **Reference contract:** `spec/openai-responses-extended.md` is authoritative for every wire shape below.
- **Run backend tests with:** `rtk pytest backend/tests/... -v`. Run migrations with `aerich migrate` + `aerich upgrade`.

---

## File Structure

**Create:**
- `backend/app/routers/openai_conversations.py` — OpenAI Conversations + items router (`prefix="/conversations"`).
- `backend/app/schemas/openai_conversations.py` — request/content schemas.
- `backend/app/services/openai/__init__.py`
- `backend/app/services/openai/identity.py` — ephemeral temp-user minting + ownership helper.
- `backend/app/services/openai/ids.py` — `conv_`/`msg_` parse/format + not-found helpers.
- `backend/app/services/openai/metadata.py` — OpenAI metadata validation.
- `backend/app/services/openai/items.py` — Message ⇄ item mapping + list-envelope builder.
- `backend/app/services/responses/retrieve.py` — reconstruct a Response object + input_items from a Message.
- Migration file under `backend/migrations/models/`.
- Tests mirroring each module under `backend/tests/`.

**Modify:**
- `backend/app/routers/conversations.py` — change `prefix="/conversations"` → `prefix="/history"` (native SPA).
- `backend/app/routers/responses.py` — add retrieve/delete/input_items + 501 stubs; mint temp-user on `POST /responses`.
- `backend/app/models/conversation.py` — `Conversation.metadata`, `Conversation.deleted_at`, `Message.deleted_at`.
- `backend/app/models/user.py` — `User.is_ephemeral`.
- `backend/app/services/responses/errors.py` — extend handler registration to the conversations router (already app-wide; verify scope).
- `backend/app/services/responses/continuity.py` — filter `deleted_at IS NULL`; accept `conv_` prefix.
- `backend/app/auth/dependencies.py` — retarget `_CONVERSATION_PATH`, `_CONVERSATION_MESSAGES_GET_PATTERN`, `_is_shared_write` to `/api/v1/history`; add `/api/v1/conversations` allowlist.
- `backend/app/main.py` — register `openai_conversations.router`; native `conversations.router` now serves `/history`.
- Frontend: `historyApi.ts`, `useRealtimeActivity.ts`, `useConversationMessages.ts`, `mocks/handlers.ts`, `HistoryPage.test.tsx`.

---

# PHASE A — Foundation (branch `feat/oai-foundation`)

Migration, namespace move, soft-delete filtering, temp-user identity. Ships independently green.

### Task A1: Schema migration — new fields

**Files:**
- Modify: `backend/app/models/user.py`, `backend/app/models/conversation.py`
- Create: migration under `backend/migrations/models/`

**Interfaces:**
- Produces: `User.is_ephemeral: bool`, `Conversation.metadata: dict`, `Conversation.deleted_at: datetime|None`, `Message.deleted_at: datetime|None`.

- [ ] **Step 1: Write the failing test**

`backend/tests/models/test_soft_delete_fields.py`:
```python
import pytest
from app.models.conversation import Conversation, Message
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def test_new_fields_exist_with_defaults():
    u = await User.create(email="a@b.c", hashed_password="!")
    assert u.is_ephemeral is False
    c = await Conversation.create(title="t", user_id=u.id)
    assert c.metadata == {}
    assert c.deleted_at is None
    m = await Message.create(conversation_id=c.id, role="user", content="hi")
    assert m.deleted_at is None
```

- [ ] **Step 2: Run to verify it fails** — `rtk pytest backend/tests/models/test_soft_delete_fields.py -v` → FAIL (`is_ephemeral`/`metadata`/`deleted_at` unknown).

- [ ] **Step 3: Add the fields**

`app/models/user.py` (after `is_active`):
```python
    is_ephemeral = fields.BooleanField(default=False)  # anonymous temp-user; prune later
```
`app/models/conversation.py` — in `Conversation`:
```python
    metadata = fields.JSONField(default=dict)          # OpenAI metadata map
    deleted_at = fields.DatetimeField(null=True)       # soft delete
```
in `Message`:
```python
    deleted_at = fields.DatetimeField(null=True)       # soft delete
```

- [ ] **Step 4: Generate + apply migration**

Run: `cd backend && aerich migrate --name oai_out_of_scope && aerich upgrade`
Expected: new migration file created and applied; no errors.

- [ ] **Step 5: Run test to verify it passes** — `rtk pytest backend/tests/models/test_soft_delete_fields.py -v` → PASS.

- [ ] **Step 6: Commit**
```bash
rtk git add backend/app/models backend/migrations backend/tests/models/test_soft_delete_fields.py
rtk git commit -m "feat: add is_ephemeral, conversation metadata, soft-delete fields"
```

---

### Task A2: Relocate native SPA router to `/api/v1/history`

**Files:**
- Modify: `backend/app/routers/conversations.py:30`, `backend/app/auth/dependencies.py`
- Test: `backend/tests/routers/test_history_router_move.py`

**Interfaces:**
- Produces: native SPA history endpoints at `/api/v1/history*`; `/api/v1/conversations` freed.

- [ ] **Step 1: Write the failing test**

`backend/tests/routers/test_history_router_move.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

pytestmark = pytest.mark.asyncio


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_history_prefix_serves_native_contract():
    async with await _client() as c:
        r = await c.get("/api/v1/history")   # native list (401 without auth, but route exists)
        assert r.status_code != 404
        # old prefix no longer served by the native router:
        r2 = await c.get("/api/v1/conversations")
        assert r2.status_code == 404  # OpenAI GET-list is not defined; only GET/{id}
```

- [ ] **Step 2: Run to verify it fails** — the old native GET `/api/v1/conversations` still answers → assertion on `r2==404` FAILS.

- [ ] **Step 3: Change the prefix**

`app/routers/conversations.py`:
```python
router = APIRouter(prefix="/history", tags=["History"])
```

- [ ] **Step 4: Retarget the auth chokepoint**

`app/auth/dependencies.py`:
```python
_MESSAGE_RATING_PATH = re.compile(r"^/api/v1/messages/[^/]+/rating$")
_HISTORY_PATH = re.compile(r"^/api/v1/history(?:/[^/]+)?$")
_HISTORY_MESSAGES_GET_PATTERN = re.compile(r"^/api/v1/history/[^/]+/messages$")
```
In `_is_shared_write`, replace the `_CONVERSATION_PATH` block:
```python
    if _HISTORY_PATH.match(path):        # all verbs: manage own history
        return True
    if method == "POST" and path == "/api/v1/conversations":  # OpenAI create (own/temp)
        return True
```
In `_is_allowed_for_basic_user`, replace `_CONVERSATION_MESSAGES_GET_PATTERN`:
```python
    if method == "GET" and _HISTORY_MESSAGES_GET_PATTERN.match(path):
        return True
```

- [ ] **Step 5: Run test to verify it passes** — `rtk pytest backend/tests/routers/test_history_router_move.py -v` → PASS. Also run existing history tests renamed: `rtk pytest backend/tests/routers -k history -v`.

- [ ] **Step 6: Commit**
```bash
rtk git add backend/app/routers/conversations.py backend/app/auth/dependencies.py backend/tests/routers/test_history_router_move.py
rtk git commit -m "refactor: move native SPA conversations router to /api/v1/history"
```

---

### Task A3: Retarget frontend callers to `/api/v1/history`

**Files:**
- Modify: `frontend/src/features/history/historyApi.ts:44,73,97`, `frontend/src/features/dashboard/useRealtimeActivity.ts:83`, `frontend/src/features/history/useConversationMessages.ts:8`, `frontend/src/mocks/handlers.ts:76,94,108,115`, `frontend/src/features/history/HistoryPage.test.tsx:34,63,98,119`

**Interfaces:**
- Consumes: backend `/api/v1/history*` from Task A2.

- [ ] **Step 1: Update the failing tests first** — in `HistoryPage.test.tsx` and `mocks/handlers.ts`, replace every `*/api/v1/conversations` with `*/api/v1/history` (keep `:id/messages` suffix).

- [ ] **Step 2: Run to verify they fail** — `cd frontend && rtk npm run test -- HistoryPage` → FAIL (app still calls `/api/v1/conversations`).

- [ ] **Step 3: Update the callers** — replace the literal `/api/v1/conversations` with `/api/v1/history` in `historyApi.ts` (3 sites), `useRealtimeActivity.ts` (1), `useConversationMessages.ts` (1).

- [ ] **Step 4: Run to verify pass** — `cd frontend && rtk npm run test -- HistoryPage` → PASS.

- [ ] **Step 5: Commit**
```bash
rtk git add frontend/src
rtk git commit -m "refactor: point history SPA calls at /api/v1/history"
```

---

### Task A4: Soft-delete filtering on existing read paths

**Files:**
- Modify: `backend/app/routers/conversations.py` (list/get/messages), `backend/app/services/responses/continuity.py:57`
- Test: `backend/tests/services/test_soft_delete_filter.py`

**Interfaces:**
- Consumes: `deleted_at` fields (A1).
- Produces: reads never return soft-deleted rows.

- [ ] **Step 1: Write the failing test**
```python
import pytest
from app.models.conversation import Conversation, Message
from app.services.responses.continuity import resolve_conversation
from app.services.responses.errors import ResponsesApiError
from app.utils import now

pytestmark = pytest.mark.asyncio


async def test_continuity_ignores_soft_deleted_assistant_message():
    c = await Conversation.create(title="t")
    m = await Message.create(conversation_id=c.id, role="assistant", content="a",
                             deleted_at=now())
    with pytest.raises(ResponsesApiError):
        await resolve_conversation(previous_response_id=f"resp_{m.id}",
                                   conversation=None, cache=None)
```

- [ ] **Step 2: Run to verify it fails** — resolves a deleted message → no raise → FAIL.

- [ ] **Step 3: Add the filter**

`continuity.py` line 57:
```python
            message = await Message.filter(
                id=message_id, role="assistant", deleted_at=None
            ).first()
```
`conversations.py` (native list/get/messages queries) — add `deleted_at=None` to the `Conversation`/`Message` filters, e.g.:
```python
    qs = Conversation.filter(deleted_at=None)
    ...
    conv = await Conversation.get_or_none(id=conversation_id, deleted_at=None)
    ...
    messages = await Message.filter(conversation_id=conversation_id, deleted_at=None).order_by("created_at")
```

- [ ] **Step 4: Run to verify pass** — `rtk pytest backend/tests/services/test_soft_delete_filter.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
rtk git add backend/app/routers/conversations.py backend/app/services/responses/continuity.py backend/tests/services/test_soft_delete_filter.py
rtk git commit -m "feat: exclude soft-deleted rows from history and continuity reads"
```

---

### Task A5: Ephemeral temp-user identity + ownership helper

**Files:**
- Create: `backend/app/services/openai/__init__.py`, `backend/app/services/openai/identity.py`
- Modify: `backend/app/routers/responses.py` (`create_response`)
- Test: `backend/tests/services/test_openai_identity.py`, `backend/tests/routers/test_responses_temp_user.py`

**Interfaces:**
- Produces:
  - `async def owner_or_ephemeral(user: User | None) -> tuple[User, str | None]` — returns the caller, or a freshly-minted ephemeral user + its JWT (token is `None` for an authenticated caller).
  - `def owns(row, user: User | None) -> bool` — `user is not None and (str(row.user_id) == str(user.id) or user.is_admin)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_openai_identity.py`:
```python
import pytest
from app.models.user import User
from app.services.openai.identity import owner_or_ephemeral, owns

pytestmark = pytest.mark.asyncio


async def test_anonymous_mints_ephemeral_user_and_token():
    user, token = await owner_or_ephemeral(None)
    assert user.is_ephemeral is True
    assert token and token.count(".") == 2  # JWT
    assert owns(type("R", (), {"user_id": user.id})(), user) is True


async def test_authenticated_caller_is_returned_unchanged():
    u = await User.create(email="real@x.y", hashed_password="!")
    user, token = await owner_or_ephemeral(u)
    assert user.id == u.id and token is None
```

- [ ] **Step 2: Run to verify it fails** — module missing → FAIL.

- [ ] **Step 3: Implement**

`backend/app/services/openai/identity.py`:
```python
"""Ephemeral temp-user identity for anonymous OpenAI-surface callers."""
from app.auth.security import create_access_token
from app.models.user import User
from app.utils import generate_uuid


async def owner_or_ephemeral(user: User | None) -> tuple[User, str | None]:
    """Return (owner, token). token is None when the caller is authenticated."""
    if user is not None:
        return user, None
    temp = await User.create(
        email=f"anon-{generate_uuid()}@ephemeral.local",
        hashed_password="!",  # unusable — no password login for temp users
        role="user",
        is_ephemeral=True,
    )
    return temp, create_access_token({"sub": str(temp.id)})


def owns(row, user: User | None) -> bool:
    if user is None:
        return False
    return str(row.user_id) == str(user.id) or user.is_admin
```

- [ ] **Step 4: Run to verify pass** — `rtk pytest backend/tests/services/test_openai_identity.py -v` → PASS.

- [ ] **Step 5: Wire temp-user into `POST /responses`**

Write `backend/tests/routers/test_responses_temp_user.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

pytestmark = pytest.mark.asyncio


async def test_anonymous_create_returns_session_header(monkeypatch):
    # (stub run_response upstream so the turn completes; see existing http tests helper)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/v1/responses", json={"input": "hi"})
        assert "X-Portal-Session" in r.headers
```

Then in `responses.py` `create_response`, for the **non-streaming** branch, resolve ownership and
attach the header:
```python
from fastapi.responses import JSONResponse
from app.services.openai.identity import owner_or_ephemeral

    owner, session_token = await owner_or_ephemeral(user)
    ...
    # non-streaming return:
    resp = JSONResponse(content=final)
    if session_token:
        resp.headers["X-Portal-Session"] = session_token
    return resp
```
For the **streaming** branch, set the header on the `StreamingResponse` the same way. Pass `owner`
(not the raw `user`) into `run_response(..., user=owner)` so anonymous turns are persisted under the
temp user.

- [ ] **Step 6: Run to verify pass** — `rtk pytest backend/tests/routers/test_responses_temp_user.py backend/tests/routers/test_responses_http.py -v` → PASS (existing tests still green).

- [ ] **Step 7: Commit**
```bash
rtk git add backend/app/services/openai backend/app/routers/responses.py backend/tests
rtk git commit -m "feat: mint ephemeral temp-user + X-Portal-Session for anonymous responses"
```

**End of Phase A.** Open PR `feat/oai-foundation` → `dev`. Update CONTEXT.md. Run `rtk pytest backend/tests -q` + frontend suite; both green before merge.

---

# PHASE B — OpenAI Conversations + Items (branch `feat/oai-conversations`)

### Task B1: id + metadata helpers

**Files:**
- Create: `backend/app/services/openai/ids.py`, `backend/app/services/openai/metadata.py`
- Test: `backend/tests/services/test_openai_ids.py`, `backend/tests/services/test_openai_metadata.py`

**Interfaces:**
- Produces:
  - `parse_uuid(raw: str, prefix: str, *, param: str, code: str) -> uuid.UUID` — strips `prefix`, parses; raises `ResponsesApiError(404, code, param)` on failure.
  - `conv_id(u) -> str` (`"conv_"+u`), `msg_id(u) -> str` (`"msg_"+u`).
  - `validate_metadata(md: dict | None) -> dict` — enforces ≤16 keys, key ≤64, value ≤512; raises `ResponsesApiError(param="metadata")`; `None` → `{}`.

- [ ] **Step 1: Write the failing tests**
```python
# test_openai_ids.py
import uuid, pytest
from app.services.openai.ids import parse_uuid, conv_id, msg_id
from app.services.responses.errors import ResponsesApiError


def test_parse_strips_prefix():
    u = uuid.uuid4()
    assert parse_uuid(f"conv_{u}", "conv_", param="conversation_id", code="conversation_not_found") == u


def test_parse_bad_id_raises_404():
    with pytest.raises(ResponsesApiError) as e:
        parse_uuid("conv_nope", "conv_", param="conversation_id", code="conversation_not_found")
    assert e.value.status == 404 and e.value.code == "conversation_not_found"


def test_format_helpers():
    assert conv_id("x") == "conv_x" and msg_id("x") == "msg_x"
```
```python
# test_openai_metadata.py
import pytest
from app.services.openai.metadata import validate_metadata
from app.services.responses.errors import ResponsesApiError


def test_none_becomes_empty():
    assert validate_metadata(None) == {}


def test_rejects_too_many_keys():
    with pytest.raises(ResponsesApiError) as e:
        validate_metadata({f"k{i}": "v" for i in range(17)})
    assert e.value.param == "metadata"
```

- [ ] **Step 2: Run to verify they fail** — modules missing → FAIL.

- [ ] **Step 3: Implement**

`app/services/openai/ids.py`:
```python
import uuid
from app.services.responses.errors import ResponsesApiError


def parse_uuid(raw: str, prefix: str, *, param: str, code: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw.removeprefix(prefix))
    except (ValueError, AttributeError):
        raise ResponsesApiError(
            f"{param.replace('_', ' ').capitalize()} '{raw}' not found",
            param=param, code=code, status=404,
        )


def conv_id(value) -> str:
    return f"conv_{value}"


def msg_id(value) -> str:
    return f"msg_{value}"
```
`app/services/openai/metadata.py`:
```python
from app.services.responses.errors import ResponsesApiError


def validate_metadata(md: dict | None) -> dict:
    if md is None:
        return {}
    if not isinstance(md, dict) or len(md) > 16:
        raise ResponsesApiError("`metadata` must be a map of at most 16 entries.",
                                param="metadata")
    for k, v in md.items():
        if not isinstance(k, str) or len(k) > 64 or not isinstance(v, str) or len(v) > 512:
            raise ResponsesApiError(
                "`metadata` keys must be ≤64 chars and values ≤512-char strings.",
                param="metadata")
    return md
```

- [ ] **Step 4: Run to verify pass** — `rtk pytest backend/tests/services/test_openai_ids.py backend/tests/services/test_openai_metadata.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
rtk git add backend/app/services/openai/ids.py backend/app/services/openai/metadata.py backend/tests/services/test_openai_ids.py backend/tests/services/test_openai_metadata.py
rtk git commit -m "feat: openai id + metadata validation helpers"
```

---

### Task B2: item mapping + list envelope

**Files:**
- Create: `backend/app/services/openai/items.py`
- Test: `backend/tests/services/test_openai_items.py`

**Interfaces:**
- Produces:
  - `item_from_message(msg) -> dict` — the `conversation.item` message shape (§6.1).
  - `flatten_content(content) -> str` — string as-is; list joins part `text` with a space; else `""`.
  - `list_envelope(items: list[dict]) -> dict` — `{object:"list", data, first_id, last_id, has_more}` (caller sets `has_more`; default False).

- [ ] **Step 1: Write the failing test**
```python
import pytest
from app.models.conversation import Conversation, Message
from app.services.openai.items import item_from_message, flatten_content, list_envelope

pytestmark = pytest.mark.asyncio


def test_flatten_content_variants():
    assert flatten_content("hi") == "hi"
    assert flatten_content([{"text": "a"}, {"text": "b"}]) == "a b"
    assert flatten_content(None) == ""


async def test_item_from_message_uses_input_text_for_user():
    c = await Conversation.create(title="t")
    m = await Message.create(conversation_id=c.id, role="user", content="q")
    item = item_from_message(m)
    assert item["id"] == f"msg_{m.id}"
    assert item["content"][0] == {"type": "input_text", "text": "q"}


def test_list_envelope_empty():
    assert list_envelope([]) == {"object": "list", "data": [],
                                 "first_id": None, "last_id": None, "has_more": False}
```

- [ ] **Step 2: Run to verify it fails** — module missing → FAIL.

- [ ] **Step 3: Implement**

`app/services/openai/items.py`:
```python
from app.services.openai.ids import msg_id

_OUTPUT_ROLES = {"assistant"}


def flatten_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join((p.get("text") or "") for p in content if isinstance(p, dict)).strip()
    return ""


def item_from_message(msg) -> dict:
    part_type = "output_text" if msg.role in _OUTPUT_ROLES else "input_text"
    return {
        "id": msg_id(msg.id),
        "type": "message",
        "role": msg.role,
        "status": "completed",
        "content": [{"type": part_type, "text": msg.content or ""}],
    }


def list_envelope(items: list[dict], *, has_more: bool = False) -> dict:
    return {
        "object": "list",
        "data": items,
        "first_id": items[0]["id"] if items else None,
        "last_id": items[-1]["id"] if items else None,
        "has_more": has_more,
    }
```

- [ ] **Step 4: Run to verify pass** — `rtk pytest backend/tests/services/test_openai_items.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
rtk git add backend/app/services/openai/items.py backend/tests/services/test_openai_items.py
rtk git commit -m "feat: message-to-item mapping and list envelope"
```

---

### Task B3: schemas + Conversations create

**Files:**
- Create: `backend/app/schemas/openai_conversations.py`, `backend/app/routers/openai_conversations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/routers/test_openai_conversations.py`

**Interfaces:**
- Consumes: `owner_or_ephemeral`/`owns` (A5), `validate_metadata` (B1), `item_from_message`/`flatten_content` (B2).
- Produces: `POST /api/v1/conversations` → conversation object + `X-Portal-Session` for anonymous.

- [ ] **Step 1: Write the failing test**
```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

pytestmark = pytest.mark.asyncio


async def _c():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_create_conversation_anonymous():
    async with await _c() as c:
        r = await c.post("/api/v1/conversations", json={"metadata": {"topic": "demo"}})
        assert r.status_code == 200
        body = r.json()
        assert body["object"] == "conversation" and body["id"].startswith("conv_")
        assert body["metadata"] == {"topic": "demo"}
        assert "X-Portal-Session" in r.headers


async def test_create_rejects_too_many_items():
    async with await _c() as c:
        r = await c.post("/api/v1/conversations",
                         json={"items": [{"role": "user", "content": "x"}] * 21})
        assert r.status_code == 400 and r.json()["error"]["param"] == "items"
```

- [ ] **Step 2: Run to verify it fails** — route missing → 404 → FAIL.

- [ ] **Step 3: Implement schemas**

`app/schemas/openai_conversations.py`:
```python
from typing import Any
from pydantic import BaseModel, ConfigDict


class MessageItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str = "message"
    role: str
    content: Any = ""


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    metadata: dict | None = None
    items: list[MessageItem] | None = None


class ConversationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    metadata: dict | None = None


class ItemsCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: list[MessageItem]
```

- [ ] **Step 4: Implement the create route**

`app/routers/openai_conversations.py`:
```python
"""OpenAI-compatible Conversations + items API. Errors use ResponsesApiError."""
import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user_optional
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.openai_conversations import (
    ConversationCreateRequest, ConversationUpdateRequest, ItemsCreateRequest,
)
from app.services.openai.identity import owner_or_ephemeral, owns
from app.services.openai.ids import conv_id, msg_id, parse_uuid
from app.services.openai.items import flatten_content, item_from_message, list_envelope
from app.services.openai.metadata import validate_metadata
from app.services.responses.errors import ResponsesApiError

router = APIRouter(prefix="/conversations", tags=["OpenAI Conversations"])

_MAX_ITEMS = 20


def _conversation_object(conv) -> dict:
    return {"id": conv_id(conv.id), "object": "conversation",
            "created_at": int(conv.created_at.timestamp()), "metadata": conv.metadata or {}}


async def _persist_items(items, conv_id_, owner) -> list[Message]:
    rows = [Message(conversation_id=conv_id_, role=i.role,
                    content=flatten_content(i.content), user_id=owner.id) for i in items]
    await Message.bulk_create(rows)
    return rows


@router.post("", summary="Create a conversation")
async def create_conversation(
    body: ConversationCreateRequest,
    user: User | None = Depends(get_current_user_optional),
):
    metadata = validate_metadata(body.metadata)
    items = body.items or []
    if len(items) > _MAX_ITEMS:
        raise ResponsesApiError(f"`items` must not exceed {_MAX_ITEMS}.", param="items")
    owner, token = await owner_or_ephemeral(user)
    conv = await Conversation.create(title="OpenAI conversation", metadata=metadata,
                                     user_id=owner.id)
    if items:
        await _persist_items(items, conv.id, owner)
    resp = JSONResponse(content=_conversation_object(conv))
    if token:
        resp.headers["X-Portal-Session"] = token
    return resp
```

Register in `app/main.py` (after the responses router):
```python
from app.routers import openai_conversations
app.include_router(openai_conversations.router, prefix="/api/v1")
```

- [ ] **Step 5: Run to verify pass** — `rtk pytest backend/tests/routers/test_openai_conversations.py -v` → PASS.

- [ ] **Step 6: Commit**
```bash
rtk git add backend/app/schemas/openai_conversations.py backend/app/routers/openai_conversations.py backend/app/main.py backend/tests/routers/test_openai_conversations.py
rtk git commit -m "feat: POST /conversations (OpenAI create)"
```

---

### Task B4–B6: Conversation retrieve / update / delete

**Files:** Modify `backend/app/routers/openai_conversations.py`; extend `test_openai_conversations.py`.

**Interfaces:**
- Produces: `_load_conversation(conversation_id, user) -> Conversation` (owner-checked, 404 on miss/foreign/deleted) reused by items routes.

- [ ] **Step 1: Write the failing tests**
```python
async def test_get_update_delete_roundtrip():
    async with await _c() as c:
        created = await c.post("/api/v1/conversations", json={"metadata": {"a": "1"}})
        cid = created.json()["id"]
        token = created.headers["X-Portal-Session"]
        h = {"Authorization": f"Bearer {token}"}

        got = await c.get(f"/api/v1/conversations/{cid}", headers=h)
        assert got.status_code == 200 and got.json()["metadata"] == {"a": "1"}

        upd = await c.post(f"/api/v1/conversations/{cid}", json={"metadata": {"b": "2"}}, headers=h)
        assert upd.json()["metadata"] == {"b": "2"}  # replace, not merge

        dele = await c.delete(f"/api/v1/conversations/{cid}", headers=h)
        assert dele.json() == {"id": cid, "object": "conversation.deleted", "deleted": True}

        gone = await c.get(f"/api/v1/conversations/{cid}", headers=h)
        assert gone.status_code == 404 and gone.json()["error"]["code"] == "conversation_not_found"


async def test_foreign_conversation_is_404_not_403():
    async with await _c() as c:
        cid = (await c.post("/api/v1/conversations", json={})).json()["id"]
        # different anonymous caller (no session token) cannot read it
        r = await c.get(f"/api/v1/conversations/{cid}")
        assert r.status_code == 404
```

- [ ] **Step 2: Run to verify they fail** — routes missing → FAIL.

- [ ] **Step 3: Implement**
```python
from app.utils import now

async def _load_conversation(conversation_id: str, user: User | None) -> Conversation:
    cid = parse_uuid(conversation_id, "conv_", param="conversation_id",
                     code="conversation_not_found")
    conv = await Conversation.get_or_none(id=cid, deleted_at=None)
    if conv is None or not owns(conv, user):
        raise ResponsesApiError(f"Conversation '{conversation_id}' not found",
                                param="conversation_id", code="conversation_not_found", status=404)
    return conv


@router.get("/{conversation_id}", summary="Retrieve a conversation")
async def get_conversation(conversation_id: str, user: User | None = Depends(get_current_user_optional)):
    return _conversation_object(await _load_conversation(conversation_id, user))


@router.post("/{conversation_id}", summary="Update a conversation")
async def update_conversation(conversation_id: str, body: ConversationUpdateRequest,
                              user: User | None = Depends(get_current_user_optional)):
    conv = await _load_conversation(conversation_id, user)
    conv.metadata = validate_metadata(body.metadata)
    await conv.save(update_fields=["metadata", "updated_at"])
    return _conversation_object(conv)


@router.delete("/{conversation_id}", summary="Delete a conversation")
async def delete_conversation(conversation_id: str, user: User | None = Depends(get_current_user_optional)):
    conv = await _load_conversation(conversation_id, user)
    stamp = now()
    conv.deleted_at = stamp
    await conv.save(update_fields=["deleted_at"])
    await Message.filter(conversation_id=conv.id, deleted_at=None).update(deleted_at=stamp)
    return {"id": conv_id(conv.id), "object": "conversation.deleted", "deleted": True}
```

- [ ] **Step 4: Run to verify pass** — `rtk pytest backend/tests/routers/test_openai_conversations.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
rtk git add backend/app/routers/openai_conversations.py backend/tests/routers/test_openai_conversations.py
rtk git commit -m "feat: conversation retrieve/update/delete (soft)"
```

---

### Task B7–B10: Items — create / list / retrieve / delete

**Files:** Modify `backend/app/routers/openai_conversations.py`; create `backend/tests/routers/test_openai_items.py`.

- [ ] **Step 1: Write the failing tests**
```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

pytestmark = pytest.mark.asyncio


async def _owned_conv():
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    created = await c.post("/api/v1/conversations", json={})
    cid = created.json()["id"]
    h = {"Authorization": f"Bearer {created.headers['X-Portal-Session']}"}
    return c, cid, h


async def test_items_crud():
    c, cid, h = await _owned_conv()
    async with c:
        made = await c.post(f"/api/v1/conversations/{cid}/items",
                            json={"items": [{"role": "user", "content": "one"},
                                            {"role": "assistant", "content": "two"}]}, headers=h)
        assert made.status_code == 200
        data = made.json()["data"]
        assert data[0]["content"][0]["type"] == "input_text"
        assert data[1]["content"][0]["type"] == "output_text"
        item_id = data[0]["id"]

        listed = await c.get(f"/api/v1/conversations/{cid}/items?order=asc&limit=1", headers=h)
        assert listed.json()["has_more"] is True and len(listed.json()["data"]) == 1

        got = await c.get(f"/api/v1/conversations/{cid}/items/{item_id}", headers=h)
        assert got.json()["id"] == item_id

        dele = await c.delete(f"/api/v1/conversations/{cid}/items/{item_id}", headers=h)
        assert dele.json() == {"id": item_id, "object": "conversation.item.deleted", "deleted": True}

        gone = await c.get(f"/api/v1/conversations/{cid}/items/{item_id}", headers=h)
        assert gone.status_code == 404 and gone.json()["error"]["code"] == "item_not_found"
```

- [ ] **Step 2: Run to verify they fail** — routes missing → FAIL.

- [ ] **Step 3: Implement**
```python
_MAX_LIMIT = 100


async def _load_item(conv, item_id: str) -> Message:
    mid = parse_uuid(item_id, "msg_", param="item_id", code="item_not_found")
    msg = await Message.get_or_none(id=mid, conversation_id=conv.id, deleted_at=None)
    if msg is None:
        raise ResponsesApiError(f"Item '{item_id}' not found",
                                param="item_id", code="item_not_found", status=404)
    return msg


@router.post("/{conversation_id}/items", summary="Create items")
async def create_items(conversation_id: str, body: ItemsCreateRequest,
                       include: list[str] | None = Query(None),
                       user: User | None = Depends(get_current_user_optional)):
    conv = await _load_conversation(conversation_id, user)
    if len(body.items) > _MAX_ITEMS:
        raise ResponsesApiError(f"`items` must not exceed {_MAX_ITEMS}.", param="items")
    rows = await _persist_items(body.items, conv.id, user or await conv)  # owner = caller
    # bulk_create doesn't refresh created_at ordering guarantees; re-read in insert order
    fresh = [await Message.get(id=r.id) for r in rows]
    return list_envelope([item_from_message(m) for m in fresh])


@router.get("/{conversation_id}/items", summary="List items")
async def list_items(conversation_id: str, limit: int = Query(20, ge=1, le=_MAX_LIMIT),
                     order: str = Query("desc"), after: str | None = Query(None),
                     include: list[str] | None = Query(None),
                     user: User | None = Depends(get_current_user_optional)):
    conv = await _load_conversation(conversation_id, user)
    qs = Message.filter(conversation_id=conv.id, deleted_at=None)
    if after:
        cursor = await _load_item(conv, after)
        op = "gt" if order == "asc" else "lt"
        qs = qs.filter(**{f"created_at__{op}": cursor.created_at})
    rows = await qs.order_by("created_at" if order == "asc" else "-created_at").limit(limit + 1)
    has_more = len(rows) > limit
    return list_envelope([item_from_message(m) for m in rows[:limit]], has_more=has_more)


@router.get("/{conversation_id}/items/{item_id}", summary="Retrieve an item")
async def get_item(conversation_id: str, item_id: str,
                   user: User | None = Depends(get_current_user_optional)):
    conv = await _load_conversation(conversation_id, user)
    return item_from_message(await _load_item(conv, item_id))


@router.delete("/{conversation_id}/items/{item_id}", summary="Delete an item")
async def delete_item(conversation_id: str, item_id: str,
                      user: User | None = Depends(get_current_user_optional)):
    conv = await _load_conversation(conversation_id, user)
    msg = await _load_item(conv, item_id)
    msg.deleted_at = now()
    await msg.save(update_fields=["deleted_at"])
    return {"id": msg_id(msg.id), "object": "conversation.item.deleted", "deleted": True}
```
> Note for implementer: fix `_persist_items` owner arg — items are owned by the caller `user` when
> present, else the conversation's owner (`conv.user_id`). Pass an explicit `owner_id`:
> change `_persist_items(items, conv_id_, owner)` to take `owner_id` and set `user_id=owner_id`;
> in `create_items` pass `owner_id=conv.user_id`.

- [ ] **Step 4: Run to verify pass** — `rtk pytest backend/tests/routers/test_openai_items.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
rtk git add backend/app/routers/openai_conversations.py backend/tests/routers/test_openai_items.py
rtk git commit -m "feat: conversation items create/list/retrieve/delete"
```

**End of Phase B.** Confirm the `ResponsesApiError` handler covers `/api/v1/conversations` (it is
registered app-wide in `register_responses_error_handler`; add a test asserting a conversations
404 returns the OpenAI envelope). Open PR → `dev`; update CONTEXT.md; full suite green.

---

# PHASE C — Response retrieve / input_items / 501 stubs (branch `feat/oai-responses-retrieve`)

### Task C1: response reconstruction service

**Files:**
- Create: `backend/app/services/responses/retrieve.py`
- Test: `backend/tests/services/test_responses_retrieve.py`

**Interfaces:**
- Produces:
  - `async def load_assistant_message(response_id: str, user) -> Message` — strips `resp_`, loads a non-deleted assistant message; owner-checked; raises `ResponsesApiError(404, "response_not_found", param="response_id")`.
  - `def response_object(msg) -> dict` — the §4 Response (status completed) reconstructed from the Message.
  - `async def input_items(msg, *, order, limit) -> dict` — list envelope of the preceding user message (§3).

- [ ] **Step 1: Write the failing test**
```python
import pytest
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.responses.errors import ResponsesApiError
from app.services.responses.retrieve import (
    input_items, load_assistant_message, response_object,
)

pytestmark = pytest.mark.asyncio


async def test_response_object_reconstructs_portal_block():
    u = await User.create(email="o@x.y", hashed_password="!")
    c = await Conversation.create(title="t", user_id=u.id)
    await Message.create(conversation_id=c.id, role="user", content="q", user_id=u.id)
    a = await Message.create(conversation_id=c.id, role="assistant", content=" ans ",
                             summary="สรุป", agency_ids=["a-1"], user_id=u.id)
    msg = await load_assistant_message(f"resp_{a.id}", u)
    body = response_object(msg)
    assert body["id"] == f"resp_{a.id}" and body["status"] == "completed"
    assert body["output_text"] == "ans" and body["portal"]["stream_version"] == "v5"
    items = await input_items(msg, order="desc", limit=20)
    assert items["data"][0]["content"][0]["text"] == "q"


async def test_foreign_owner_is_not_found():
    owner = await User.create(email="p@x.y", hashed_password="!")
    other = await User.create(email="q@x.y", hashed_password="!")
    c = await Conversation.create(title="t", user_id=owner.id)
    a = await Message.create(conversation_id=c.id, role="assistant", content="x", user_id=owner.id)
    with pytest.raises(ResponsesApiError) as e:
        await load_assistant_message(f"resp_{a.id}", other)
    assert e.value.status == 404 and e.value.code == "response_not_found"
```

- [ ] **Step 2: Run to verify it fails** — module missing → FAIL.

- [ ] **Step 3: Implement**

`app/services/responses/retrieve.py`:
```python
"""Reconstruct a Response object and its input_items from a stored Message."""
from app.models.conversation import Message
from app.services.openai.identity import owns
from app.services.openai.ids import parse_uuid
from app.services.openai.items import item_from_message, list_envelope
from app.services.responses.errors import ResponsesApiError

_ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def _not_found(response_id: str) -> ResponsesApiError:
    return ResponsesApiError(f"Response with id '{response_id}' not found",
                             param="response_id", code="response_not_found", status=404)


async def load_assistant_message(response_id: str, user) -> Message:
    try:
        mid = parse_uuid(response_id, "resp_", param="response_id", code="response_not_found")
    except ResponsesApiError:
        raise _not_found(response_id)
    msg = await Message.get_or_none(id=mid, role="assistant", deleted_at=None)
    if msg is None or not owns(msg, user):
        raise _not_found(response_id)
    return msg


def response_object(msg) -> dict:
    answer = (msg.content or "").strip()
    summary = (msg.summary or "").strip()
    body = {
        "id": f"resp_{msg.id}",
        "object": "response",
        "created_at": int(msg.created_at.timestamp()),
        "status": "completed",
        "model": "thai-citizen-guide",  # not persisted per-turn; echo the default id
        "output": [],
        "output_text": answer,
        "usage": dict(_ZERO_USAGE),
        "portal": {
            "conversation_id": str(msg.conversation_id),
            "summary": summary,
            "references": msg.summary_references or [],
            "agency_ids": msg.agency_ids or [],
            "cached": False,                       # not persisted; best-effort
            "stream_version": "v5" if summary else "v4",
        },
    }
    if answer:
        body["output"] = [{
            "id": f"msg_{msg.id}", "type": "message", "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": answer, "annotations": []}],
        }]
    return body


async def input_items(msg, *, order: str, limit: int) -> dict:
    prior = (await Message.filter(conversation_id=msg.conversation_id, role="user",
                                  deleted_at=None, created_at__lt=msg.created_at)
             .order_by("-created_at").first())
    return list_envelope([item_from_message(prior)] if prior else [])
```

- [ ] **Step 4: Run to verify pass** — `rtk pytest backend/tests/services/test_responses_retrieve.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
rtk git add backend/app/services/responses/retrieve.py backend/tests/services/test_responses_retrieve.py
rtk git commit -m "feat: reconstruct Response object + input_items from Message"
```

---

### Task C2: retrieve / delete / input_items routes

**Files:**
- Modify: `backend/app/routers/responses.py`
- Test: `backend/tests/routers/test_responses_retrieve_route.py`

- [ ] **Step 1: Write the failing test**
```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.auth.security import create_access_token

pytestmark = pytest.mark.asyncio


async def _owned():
    u = await User.create(email="r@x.y", hashed_password="!")
    c = await Conversation.create(title="t", user_id=u.id)
    await Message.create(conversation_id=c.id, role="user", content="q", user_id=u.id)
    a = await Message.create(conversation_id=c.id, role="assistant", content="ans", user_id=u.id)
    return u, a


async def test_retrieve_delete_input_items():
    u, a = await _owned()
    h = {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        got = await c.get(f"/api/v1/responses/resp_{a.id}", headers=h)
        assert got.status_code == 200 and got.json()["output_text"] == "ans"

        items = await c.get(f"/api/v1/responses/resp_{a.id}/input_items", headers=h)
        assert items.json()["data"][0]["content"][0]["text"] == "q"

        dele = await c.delete(f"/api/v1/responses/resp_{a.id}", headers=h)
        assert dele.json() == {"id": f"resp_{a.id}", "object": "response", "deleted": True}

        gone = await c.get(f"/api/v1/responses/resp_{a.id}", headers=h)
        assert gone.status_code == 404 and gone.json()["error"]["code"] == "response_not_found"
```

- [ ] **Step 2: Run to verify it fails** — routes missing → FAIL.

- [ ] **Step 3: Implement** — add to `responses.py` (after `create_response`):
```python
from fastapi import Query
from app.services.responses.retrieve import (
    input_items as build_input_items, load_assistant_message, response_object,
)
from app.utils import now


@router.get("/{response_id}", summary="Retrieve a response")
async def get_response(response_id: str, user: User | None = Depends(get_current_user_optional)):
    return response_object(await load_assistant_message(response_id, user))


@router.delete("/{response_id}", summary="Delete a response")
async def delete_response(response_id: str, user: User | None = Depends(get_current_user_optional)):
    msg = await load_assistant_message(response_id, user)
    msg.deleted_at = now()
    await msg.save(update_fields=["deleted_at"])
    return {"id": f"resp_{msg.id}", "object": "response", "deleted": True}


@router.get("/{response_id}/input_items", summary="List a response's input items")
async def response_input_items(response_id: str, limit: int = Query(20, ge=1, le=100),
                               order: str = Query("desc"),
                               after: str | None = Query(None),
                               user: User | None = Depends(get_current_user_optional)):
    msg = await load_assistant_message(response_id, user)
    return await build_input_items(msg, order=order, limit=limit)
```
> Route-ordering note: FastAPI matches in declaration order. `POST ""` is unaffected. Ensure the
> new `GET /{response_id}` sits **after** any static sub-paths you add in C5 (`/input_tokens`,
> `/compact`) so those aren't captured as a `response_id`. Declare the static POST stubs first.

- [ ] **Step 4: Run to verify pass** — `rtk pytest backend/tests/routers/test_responses_retrieve_route.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
rtk git add backend/app/routers/responses.py backend/tests/routers/test_responses_retrieve_route.py
rtk git commit -m "feat: GET/DELETE /responses/{id} + input_items"
```

---

### Task C3: Kind 2 501 stubs

**Files:**
- Modify: `backend/app/routers/responses.py`, `backend/app/services/responses/errors.py` (confirm 501 flows through)
- Test: `backend/tests/routers/test_responses_stubs.py`

- [ ] **Step 1: Write the failing test**
```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("method,path,code", [
    ("post", "/api/v1/responses/resp_x/cancel", "not_implemented"),
    ("post", "/api/v1/responses/input_tokens", "not_implemented"),
    ("post", "/api/v1/responses/compact", "not_implemented"),
])
async def test_kind2_stubs_return_501(method, path, code):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await getattr(c, method)(path, json={"model": "thai-citizen-guide"})
        assert r.status_code == 501
        assert r.json()["error"]["code"] == code
        assert r.json()["error"]["type"] == "invalid_request_error"
```

- [ ] **Step 2: Run to verify it fails** — routes missing (405/404) → FAIL.

- [ ] **Step 3: Implement** — declare these **before** `GET /{response_id}` in `responses.py`:
```python
def _not_implemented(message: str) -> ResponsesApiError:
    return ResponsesApiError(message, code="not_implemented", status=501)


@router.post("/input_tokens", summary="(unsupported) token counting")
async def input_tokens_stub(body: dict | None = None):
    raise _not_implemented("`input_tokens` is not supported: OneChat does not report "
                           "token counts to the portal.")


@router.post("/compact", summary="(unsupported) compaction")
async def compact_stub(body: dict | None = None):
    raise _not_implemented("`compact` is not supported: OneChat owns context/history "
                           "server-side.")


@router.post("/{response_id}/cancel", summary="(unsupported) cancel")
async def cancel_stub(response_id: str):
    raise _not_implemented("`cancel` is not supported: a turn is one synchronous OneChat "
                           "call with no background mode to cancel.")
```
Verify `ResponsesApiError(status=501)` renders via the existing handler (it uses `exc.status`
directly, so 501 already works — no change to `errors.py` needed; add a one-line comment noting
501 is intentional).

- [ ] **Step 4: Run to verify pass** — `rtk pytest backend/tests/routers/test_responses_stubs.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
rtk git add backend/app/routers/responses.py backend/tests/routers/test_responses_stubs.py
rtk git commit -m "feat: 501 stubs for cancel/input_tokens/compact"
```

---

### Task C4: Flip the base spec + CONTEXT.md

**Files:**
- Modify: `spec/openai-responses.md` (endpoint-scope tables), `CONTEXT.md`

- [ ] **Step 1** — In `spec/openai-responses.md`, change the §"Endpoint scope" and §5.1/§8.1 rows for the now-implemented endpoints from ❌ to ✅ (or "501 stub"), and add a top-of-file cross-link: `See spec/openai-responses-extended.md for retrieve/delete/input_items, Conversations, items, and the Kind 2 501 stubs.` Leave the 44 streaming events unchanged.

- [ ] **Step 2** — Update `CONTEXT.md`: note the `/api/v1/history` move, the OpenAI conversations router, temp-user identity, and soft delete.

- [ ] **Step 3: Commit**
```bash
rtk git add spec/openai-responses.md spec/openai-responses-extended.md CONTEXT.md
rtk git commit -m "docs: flip out-of-scope rows; document extended surface"
```

**End of Phase C.** Open PR → `dev`. Full backend + frontend suites green; run docker per CLAUDE.md before merge.

---

## Self-Review (spec coverage)

| Extended-spec section | Task(s) |
|---|---|
| §0.1 namespace move | A2, A3 |
| §0.2 temp-user auth + header | A5, B3 |
| §0.3 soft delete | A1, A4, B6, B10, C2 |
| §0.4 id prefixes | B1, C1 |
| §0.5 schemas | B3 |
| §1 retrieve | C1, C2 |
| §2 delete | C2 |
| §3 input_items | C1, C2 |
| §4 501 stubs | C3 |
| §5 conversations CRUD | B3, B4–B6 |
| §6 items CRUD + mapping | B2, B7–B10 |
| §7 error envelope + codes | B1, C1, C3; handler-scope test in Phase B wrap-up |
| §8 out-of-scope unchanged | C4 (no new events) |

**Open items flagged for the implementer:**
1. `_persist_items` owner arg fix (noted inline in B7–B10) — items owned by `conv.user_id`.
2. Ephemeral-user pruning is out of scope (flag only; JWT TTL bounds exposure).
3. `response_object` reconstructs `model`/`cached`/`stream_version` heuristically (not persisted per-turn) — documented in extended-spec §1.
