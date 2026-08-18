# Message Repository Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add `app/repositories/message.py` and route the Message *command* access through it, removing Active-Record ORM calls and `DoesNotExist` from the core use-case services. Message's heavy analytics/reporting reads and the raw pg_trgm similarity SQL stay in the read-model (out of scope).

**Architecture:** Fourth application of the repository template (see spec). Command repository only; no `Protocol`; returns/accepts Tortoise `Message` instances. The service keeps building `Message(...)` rows for `bulk_create` (the repo owns the DB op, not the object construction — same shape as Agency's `update_from_dict`).

**Tech Stack:** Python 3, uv, pytest + pytest-asyncio, Tortoise ORM.

**Spec:** `docs/superpowers/specs/2026-08-18-repository-ports-design.md`

## Global Constraints

- Test commands: full suite `cd backend && uv run pytest`; one file `cd backend && uv run pytest <path> -v`.
- Behavior-preserving refactor. Baseline: 730 passed / 2 skipped. After Task 1 expect ~737.
- Branch: `refactor/repo-port-message` (already checked out).
- TDD mandatory. American English. YAGNI — only the methods below.
- Keep any `Message` import still used in type annotations or for row construction (`conversation.py` builds `Message(...)` rows and annotates `list[Message]`; `message.py` annotates `-> Message`). Drop `Message`/`DoesNotExist` imports only where they become unreferenced (verify per file).
- **Scope this branch (5 files):** `services/chat/turn.py`, `services/conversation.py` (Message parts), `services/message.py`, `services/session.py`, `services/chat/llm.py`. OUT OF SCOPE (read-model / later): `similarity.py` (raw pg_trgm SQL + its `Message.get`), `feedback.py`, all analytics `.values()`/RawSQL reads (`analytics/*`), and `chat/stream.py`'s `Message` type-hint-only usage.

---

### Task 1: Create the Message command repository (TDD)

**Files:**
- Create: `backend/app/repositories/message.py`
- Test: `backend/tests/repositories/test_message_repo.py`

**Interfaces produced:**
```python
async def by_id(message_id) -> Message | None
async def list_for_conversation(conversation_id, *, include_deleted=False) -> list[Message]
async def first_user_message(conversation_id) -> Message | None
async def create(**fields) -> Message
async def bulk_create(rows, *, ignore_conflicts=False) -> None
async def set_category(message_id, category) -> None
async def save(message, *, update_fields=None) -> None
```

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/repositories/test_message_repo.py`:
```python
import pytest

from app.models.conversation import Conversation, Message
from app.repositories import message as repo
from app.utils import now


async def _conv():
    return await Conversation.create(title="t", agencies=[], status="active")


@pytest.mark.asyncio
async def test_by_id_present_and_absent(db):
    c = await _conv()
    m = await repo.create(conversation_id=c.id, role="user", content="hi")
    assert (await repo.by_id(m.id)).id == m.id
    assert await repo.by_id("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_list_for_conversation_orders_and_excludes_deleted(db):
    c = await _conv()
    await repo.create(conversation_id=c.id, role="user", content="first")
    await repo.create(conversation_id=c.id, role="assistant", content="second")
    await repo.create(conversation_id=c.id, role="user", content="gone", deleted_at=now())
    rows = await repo.list_for_conversation(c.id)
    assert [m.content for m in rows] == ["first", "second"]          # deleted excluded, created_at order
    rows_all = await repo.list_for_conversation(c.id, include_deleted=True)
    assert len(rows_all) == 3


@pytest.mark.asyncio
async def test_first_user_message(db):
    c = await _conv()
    await repo.create(conversation_id=c.id, role="assistant", content="a")
    await repo.create(conversation_id=c.id, role="user", content="u1")
    await repo.create(conversation_id=c.id, role="user", content="u2")
    first = await repo.first_user_message(c.id)
    assert first.content == "u1"                                     # earliest user message
    assert await repo.first_user_message("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_set_category_by_id(db):
    c = await _conv()
    m = await repo.create(conversation_id=c.id, role="user", content="q")
    await repo.set_category(m.id, "travel")
    assert (await repo.by_id(m.id)).category == "travel"


@pytest.mark.asyncio
async def test_bulk_create_ignore_conflicts(db):
    c = await _conv()
    rows = [
        Message(conversation_id=c.id, role="user", content="b1"),
        Message(conversation_id=c.id, role="assistant", content="b2"),
    ]
    await repo.bulk_create(rows, ignore_conflicts=True)
    assert len(await repo.list_for_conversation(c.id)) == 2


@pytest.mark.asyncio
async def test_save_partial(db):
    c = await _conv()
    m = await repo.create(conversation_id=c.id, role="assistant", content="a")
    m.rating = "up"
    await repo.save(m, update_fields=["rating"])
    assert (await repo.by_id(m.id)).rating == "up"
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd backend && uv run pytest tests/repositories/test_message_repo.py -v`
Expected: FAIL/ERROR — `app.repositories.message` does not exist.

- [ ] **Step 3: Implement the repository**

Create `backend/app/repositories/message.py`:
```python
from __future__ import annotations

from app.models.conversation import Message


async def by_id(message_id) -> Message | None:
    return await Message.get_or_none(id=message_id)


async def list_for_conversation(conversation_id, *, include_deleted: bool = False) -> list[Message]:
    qs = Message.filter(conversation_id=conversation_id)
    if not include_deleted:
        qs = qs.filter(deleted_at=None)
    return await qs.order_by("created_at")


async def first_user_message(conversation_id) -> Message | None:
    return await (
        Message.filter(conversation_id=conversation_id, role="user")
        .order_by("created_at")
        .first()
    )


async def create(**fields) -> Message:
    return await Message.create(**fields)


async def bulk_create(rows, *, ignore_conflicts: bool = False) -> None:
    await Message.bulk_create(rows, ignore_conflicts=ignore_conflicts)


async def set_category(message_id, category) -> None:
    await Message.filter(id=message_id).update(category=category)


async def save(message: Message, *, update_fields: list[str] | None = None) -> None:
    await message.save(update_fields=update_fields)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd backend && uv run pytest tests/repositories/test_message_repo.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add backend/app/repositories/message.py backend/tests/repositories/test_message_repo.py
git commit -m "feat(repositories): add Message command repository

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Route Message command access through the repository

**Files (modify):** `backend/app/services/chat/turn.py`, `backend/app/services/conversation.py`, `backend/app/services/message.py`, `backend/app/services/session.py`, `backend/app/services/chat/llm.py`

**Interfaces consumed:** the Task 1 functions. Add `from app.repositories import message as message_repo` to each modified file.

- [ ] **Step 1: `chat/turn.py`** — both `await Message.create(...)` calls (user_msg and asst_msg) → `await message_repo.create(...)` (same kwargs). Then drop the `Message` import if now unreferenced (verify — `Conversation` was already dropped in a prior branch; `Message` is likely used only in these two creates). Keep everything inside `async with in_transaction():`.

- [ ] **Step 2: `conversation.py`** — `await Message.bulk_create(msg_rows, ignore_conflicts=True)` → `await message_repo.bulk_create(msg_rows, ignore_conflicts=True)`. The two `Message.filter(conversation_id=..., deleted_at=None).order_by("created_at")` (in `get_conversation_with_messages` and `get_conversation_messages`) → `await message_repo.list_for_conversation(conversation_id)`. KEEP the `Message` import — it is still used to build `msg_rows` (`Message(id=..., ...)` list comprehension in `create_conversation`) and in `list[Message]` annotations.

- [ ] **Step 3: `message.py`** — `try: msg = await Message.get(id=message_id) except DoesNotExist: raise ApiError(NOT_FOUND, 404)` →
  ```python
  msg = await message_repo.by_id(message_id)
  if msg is None:
      raise ApiError(ErrorCode.NOT_FOUND, "Message not found", status=404)
  ```
  `await msg.save(update_fields=update_fields)` → `await message_repo.save(msg, update_fields=update_fields)`. Remove `from tortoise.exceptions import DoesNotExist` (now unused). KEEP `Message` (annotation `-> Message`) and the existing `agency_repo` import.

- [ ] **Step 4: `session.py`** — the `first_msg = await Message.filter(conversation_id=conversation.id, role="user").order_by("created_at").first()` block → `first_msg = await message_repo.first_user_message(conversation.id)`. Keep the `if first_msg is None:` handling. Drop `Message` from `from app.models.conversation import Conversation, Message` (KEEP `Conversation` — used in the param annotation) if `Message` is now unreferenced (verify).

- [ ] **Step 5: `chat/llm.py`** — `await Message.filter(id=message_id).update(category=res.content)` → `await message_repo.set_category(message_id, res.content)`. Drop the `Message` import if now unreferenced (verify).

- [ ] **Step 6: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: PASS, 737 passed / 2 skipped (730 + ~6 repo tests → 736; state the exact number). No FAIL/ERROR.

- [ ] **Step 7: Prove the in-scope Message command access is ORM-free**

Run: `cd backend && grep -rnE 'Message\.(get|get_or_none|filter|create|bulk_create)|msg\.save\(' app/services/chat/turn.py app/services/conversation.py app/services/message.py app/services/session.py app/services/chat/llm.py`
Expected: NO matches. (`Message(...)` bare construction in conversation.py is a DIFFERENT token — a constructor call, not `Message.<orm>` — and is allowed.)

Run: `cd backend && grep -rn 'DoesNotExist' app/services/message.py`
Expected: no matches.

- [ ] **Step 8: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add backend/app/services/chat/turn.py backend/app/services/conversation.py backend/app/services/message.py backend/app/services/session.py backend/app/services/chat/llm.py
git commit -m "refactor: route Message command access through the repository

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** repo surface derived from the real command sites (create/bulk_create/by_id/list-for-conversation/first-user-message/set-category/save); analytics/similarity reads deferred to the read-model.
- **No placeholders:** exact repo code, exact tests, exact per-site mappings.
- **Type/name consistency:** the 7 method names used identically in Task 1 and Task 2.
- **Behavior preserved:** `list_for_conversation` keeps `deleted_at=None` + `created_at` order; `set_category` stays an `update()`-by-id (no load); `bulk_create` keeps `ignore_conflicts=True`; `save` partial-update shape preserved.
