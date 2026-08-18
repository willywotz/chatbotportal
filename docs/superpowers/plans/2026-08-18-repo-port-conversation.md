# Conversation Repository Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Introduce `app/repositories/conversation.py` and route all Conversation *command* access through it, removing Active-Record ORM calls and `DoesNotExist` from the use-case services.

**Architecture:** A command repository (module of async functions wrapping Tortoise) is the data-access seam. Use-case services call it instead of `Conversation.get/filter/create/save/delete`. Repositories return/accept Tortoise model instances (isolate ORM operations + exceptions, not the model type). No `Protocol` (one impl; SQLite-backed tests). Analytics Conversation reads and all `Message` access are out of scope.

**Tech Stack:** Python 3, uv, pytest + pytest-asyncio, Tortoise ORM.

**Spec:** `docs/superpowers/specs/2026-08-18-repository-ports-design.md`

## Global Constraints

- Test commands: full suite `cd backend && uv run pytest`; one file `cd backend && uv run pytest <path> -v`.
- Behavior-preserving refactor: the existing conversation/chat/session test suite must stay green. Baseline: 716 passed / 2 skipped.
- Branch: `refactor/repo-port-conversation` (already checked out).
- TDD mandatory. American English names. YAGNI — only the methods below.
- Repositories return/accept Tortoise `Conversation` instances (deliberate `withinlazy` ceiling — do not build entity mapping).
- Do NOT touch `Message` access or analytics `Conversation.filter(created_at__month...).count()` reads — later steps.

---

### Task 1: Create the Conversation command repository (TDD)

**Files:**
- Create: `backend/app/repositories/__init__.py` (empty)
- Create: `backend/app/repositories/conversation.py`
- Test: `backend/tests/repositories/test_conversation_repo.py` (+ `backend/tests/repositories/__init__.py` if the test dirs need it — match the existing test layout; `tests/services/` has no `__init__.py` per package style, follow whatever `tests/` uses)

**Interfaces produced (later tasks rely on these exact signatures):**
```python
async def by_id(conversation_id, *, exclude_deleted: bool = False) -> Conversation | None
async def list_and_count(*, user_id, title_contains, agency_contains,
                         created_from, created_to, offset, limit) -> tuple[list[Conversation], int]
async def create(**fields) -> Conversation
async def save(conv, *, update_fields: list[str] | None = None) -> None
async def delete(conv) -> None
```

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/repositories/test_conversation_repo.py`:
```python
import pytest

from app.models.user import User
from app.repositories import conversation as repo
from app.utils import now


@pytest.mark.asyncio
async def test_by_id_present_and_absent(db):
    c = await repo.create(title="t", agencies=[], status="active")
    assert (await repo.by_id(c.id)).id == c.id
    assert await repo.by_id("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_by_id_exclude_deleted(db):
    c = await repo.create(title="t", agencies=[], status="active", deleted_at=now())
    assert await repo.by_id(c.id) is not None                       # no filter → found
    assert await repo.by_id(c.id, exclude_deleted=True) is None      # filtered out


@pytest.mark.asyncio
async def test_list_and_count_filters_and_pages(db):
    u = await User.create(email="o@x.com", hashed_password="h", role="user")
    for i in range(3):
        await repo.create(title=f"keep {i}", agencies=[], status="active", user_id=u.id)
    await repo.create(title="other", agencies=[], status="active", user_id=u.id)
    rows, total = await repo.list_and_count(
        user_id=u.id, title_contains="keep", agency_contains=None,
        created_from=None, created_to=None, offset=0, limit=2)
    assert total == 3 and len(rows) == 2                             # total is pre-page count


@pytest.mark.asyncio
async def test_save_partial_and_delete(db):
    c = await repo.create(title="t", agencies=[], status="active")
    c.external_session_id = "sess-1"
    await repo.save(c, update_fields=["external_session_id"])
    assert (await repo.by_id(c.id)).external_session_id == "sess-1"
    await repo.delete(c)
    assert await repo.by_id(c.id) is None
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd backend && uv run pytest tests/repositories/test_conversation_repo.py -v`
Expected: FAIL/ERROR — `app.repositories.conversation` does not exist.

- [ ] **Step 3: Implement the repository**

Create `backend/app/repositories/__init__.py` (empty file).

Create `backend/app/repositories/conversation.py`:
```python
from __future__ import annotations

from app.models.conversation import Conversation


async def by_id(conversation_id, *, exclude_deleted: bool = False) -> Conversation | None:
    filters: dict = {"id": conversation_id}
    if exclude_deleted:
        filters["deleted_at"] = None
    return await Conversation.get_or_none(**filters)


async def list_and_count(
    *, user_id, title_contains: str | None, agency_contains: str | None,
    created_from, created_to, offset: int | None, limit: int | None,
) -> tuple[list[Conversation], int]:
    qs = Conversation.filter(deleted_at=None)
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    if title_contains:
        qs = qs.filter(title__icontains=title_contains)
    if agency_contains:
        qs = qs.filter(agencies__contains=agency_contains)
    if created_from is not None:
        qs = qs.filter(created_at__gte=created_from)
    if created_to is not None:
        qs = qs.filter(created_at__lt=created_to)
    total = await qs.count()
    page_qs = qs.order_by("-created_at")
    if limit is not None:
        page_qs = page_qs.offset(offset or 0).limit(limit)
    return await page_qs, total


async def create(**fields) -> Conversation:
    return await Conversation.create(**fields)


async def save(conv: Conversation, *, update_fields: list[str] | None = None) -> None:
    await conv.save(update_fields=update_fields)


async def delete(conv: Conversation) -> None:
    await conv.delete()
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd backend && uv run pytest tests/repositories/test_conversation_repo.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add backend/app/repositories/ backend/tests/repositories/
git commit -m "feat(repositories): add Conversation command repository

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Route Conversation command access through the repository

**Files (modify):**
- `backend/app/services/conversation.py`
- `backend/app/services/chat/turn.py`
- `backend/app/services/chat/stream.py`
- `backend/app/services/session.py`

**Interfaces consumed:** the Task 1 functions above.

**Rule:** behavior-preserving. Read each file, apply the change, keep the full suite green. Add `from app.repositories import conversation as conversation_repo` to each modified file. Remove now-unused imports (`Conversation` from `app.models`, and `tortoise.exceptions.DoesNotExist` where it was only used for Conversation).

- [ ] **Step 1: Refactor `app/services/conversation.py`**

  - Drop `Conversation` from `from app.models.conversation import Conversation, Message` (keep `Message`). Remove `from tortoise.exceptions import DoesNotExist`. Add the repo import.
  - `create_conversation`: `await Conversation.create(...)` → `await conversation_repo.create(...)` (same kwargs).
  - `_authorize`: `await Conversation.get_or_none(id=conversation_id, deleted_at=None)` → `await conversation_repo.by_id(conversation_id, exclude_deleted=True)`.
  - `delete_conversation`: replace the `try: conv = await Conversation.get(id=conversation_id) except DoesNotExist: raise ApiError(...)` with:
    ```python
    conv = await conversation_repo.by_id(conversation_id)
    if conv is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Conversation not found", status=404)
    ```
    and `await conv.delete()` → `await conversation_repo.delete(conv)`.
  - `list_conversations`: keep the date-parse validation (raising `ApiError`) and the admin check, but move the query to the repo. Replace the body from `qs = Conversation.filter(...)` through `return rows, total` with:
    ```python
    created_from = None
    if date_from:
        try:
            created_from = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise ApiError(ErrorCode.INVALID_REQUEST, "date_from must be YYYY-MM-DD", status=400)
    created_to = None
    if date_to:
        try:
            created_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            raise ApiError(ErrorCode.INVALID_REQUEST, "date_to must be YYYY-MM-DD", status=400)

    return await conversation_repo.list_and_count(
        user_id=None if user.is_admin else user.id,
        title_contains=search or None,
        agency_contains=filter_agency or None,
        created_from=created_from,
        created_to=created_to,
        offset=(page - 1) * page_size if page_size is not None else None,
        limit=page_size,
    )
    ```

- [ ] **Step 2: Refactor `app/services/chat/turn.py`**

  Drop `Conversation` from the models import (keep `Message`). Remove `from tortoise.exceptions import DoesNotExist` (verify it is used nowhere else in the file — if it is, keep it). Add the repo import. Replace the try/except block (currently lines ~52-72) inside `async with in_transaction():` with:
  ```python
  conv = await conversation_repo.by_id(conversation_id)
  if conv is None:
      conv = await conversation_repo.create(
          id=conversation_id,
          title=(title or query)[: settings.TITLE_MAX_LENGTH],
          preview=query[: settings.PREVIEW_MAX_LENGTH],
          agencies=[],
          status=status,
          message_count=2,
          response_time=response_time,
          user_id=user.id if user else None,
          external_session_id=external_session_id,
      )
  else:
      conv.message_count += 2
      conv.updated_at = now()
      if not succeeded:
          # One-way ratchet: once "failed", status is never restored to "success",
          # keeping the conversation out of the similarity cache on recovery.
          conv.status = "failed"
      await conversation_repo.save(conv)
  ```
  Leave the surrounding `async with in_transaction():`, the two `Message.create(...)` calls, and the return unchanged. (Repo calls run inside the same transaction — Tortoise binds the connection via contextvars.)

- [ ] **Step 3: Refactor `app/services/chat/stream.py`**

  In `prepare_turn`, replace:
  ```python
  try:
      conv = await Conversation.get(id=conversation_id)
  except DoesNotExist:
      raise ConversationNotFound(conversation_id)
  ```
  with:
  ```python
  conv = await conversation_repo.by_id(conversation_id)
  if conv is None:
      raise ConversationNotFound(conversation_id)
  ```
  Drop `from app.models.conversation import Conversation, Message` down to just `Message` if `Conversation` is now unused (it is — only `prepare_turn` used it). Remove `from tortoise.exceptions import DoesNotExist` if now unused in the file (verify). Add the repo import. `Message` and `User`/`ConnectionLog` imports stay (later steps).

- [ ] **Step 4: Refactor `app/services/session.py`**

  Add the repo import. Replace `await conversation.save(update_fields=["external_session_id"])` with `await conversation_repo.save(conversation, update_fields=["external_session_id"])`. The function still receives a `Conversation` instance from its caller — that type hint and the `Message` import stay (later steps).

- [ ] **Step 5: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: PASS, 720 passed / 2 skipped (716 baseline + 4 new repo tests). No FAIL/ERROR.

- [ ] **Step 6: Prove Conversation command access is ORM-free in the services**

Run: `cd backend && grep -rnE 'Conversation\.(get|get_or_none|filter|create)|conv\.save\(|conv\.delete\(|conversation\.save\(' app/services`
Expected: the only remaining `Conversation.filter(...)` matches are the analytics `created_at__month/__year/__gte ... .count()` reads (brief.py, heatmap.py) — out of scope. No `Conversation.get/get_or_none/create`, no `conv.save/delete` in the refactored files.

Run: `cd backend && grep -rn 'DoesNotExist' app/services/conversation.py app/services/chat/turn.py app/services/chat/stream.py`
Expected: no matches.

- [ ] **Step 7: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add backend/app/services/conversation.py backend/app/services/chat/turn.py backend/app/services/chat/stream.py backend/app/services/session.py
git commit -m "refactor: route Conversation command access through the repository

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** repository surface (Task 1) matches the spec §4; all seven refactor rows in spec §5 are covered by Task 2 Steps 1-4 (conversation.py ×4 sites, turn.py, stream.py, session.py).
- **No placeholders:** exact repo code, exact test code, exact save_turn replacement given; simpler sites specified by exact before/after.
- **Type/name consistency:** `by_id`, `list_and_count`, `create`, `save`, `delete` used identically in Task 1 signatures and Task 2 call sites.
- **Out of scope preserved:** Message access and analytics Conversation counts explicitly left; the grep in Step 6 tolerates the analytics `Conversation.filter().count()` reads.
