# Agency Repository Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add `app/repositories/agency.py` and route the core Agency *command* access through it — including the atomic `total_calls` counter, which becomes the template's first `increment_*` method (NOT a mutate-then-`save()`).

**Architecture:** Third application of the repository template (see spec). This one extends it: an aggregate with an atomic counter gets a dedicated `increment_calls()` method (`F("total_calls")+1` + refresh) instead of routing a counter through `save()`. Command repository only; no `Protocol`; returns/accepts Tortoise instances.

**Tech Stack:** Python 3, uv, pytest + pytest-asyncio, Tortoise ORM.

**Spec:** `docs/superpowers/specs/2026-08-18-repository-ports-design.md`

## Global Constraints

- Test commands: full suite `cd backend && uv run pytest`; one file `cd backend && uv run pytest <path> -v`.
- Behavior-preserving refactor. Baseline: 726 passed / 2 skipped. After Task 1 (+repo tests) expect ~732.
- Branch: `refactor/repo-port-agency` (already checked out).
- TDD mandatory. American English. YAGNI — only the methods below.
- Keep any `Agency` import still used in type annotations. Keep `from tortoise.exceptions import DoesNotExist` in `message.py` (still used for the `Message` lookup there — do NOT remove it).
- **Scope this branch:** `services/agency.py`, `services/message.py` (Agency rating write only), `services/seed.py` (Agency create/count only). OUT OF SCOPE (documented follow-ups): the peripheral single Agency sites in `agency_lifecycle.py`, `conformance.py`, `connection_log.py`, `feedback.py`, `popular_questions.py`, `agency_reconcile.py`, `scheduler.py`, and ALL analytics `.values()` reads (`analytics/*`, `mcp/server.py`, `public_status.py`). Those adopt the repo in a later branch.
- **Behavior note:** the `rating_up`/`rating_down` write in `message.py` stays a non-atomic read-modify-`save()` (its existing, documented behavior — Go parity was only for `total_calls`). This branch routes it through the repo unchanged; making it atomic is a separate future change, not part of this refactor.

---

### Task 1: Create the Agency command repository (TDD)

**Files:**
- Create: `backend/app/repositories/agency.py`
- Test: `backend/tests/repositories/test_agency_repo.py`

**Interfaces produced:**
```python
async def by_id(agency_id) -> Agency | None
async def list_and_count(*, status, connection_type, search_text) -> tuple[list[Agency], int]
async def create(**fields) -> Agency
async def save(agency, *, update_fields: list[str] | None = None) -> None
async def delete(agency) -> None
async def increment_calls(agency) -> Agency
async def count_all() -> int
```

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/repositories/test_agency_repo.py`:
```python
import pytest

from app.repositories import agency as repo


async def _mk(name, **kw):
    return await repo.create(name=name, **kw)


@pytest.mark.asyncio
async def test_by_id_present_and_absent(db):
    a = await _mk("DGA", status="active")
    assert (await repo.by_id(a.id)).id == a.id
    assert await repo.by_id("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_list_and_count_filters(db):
    await _mk("Active One", status="active", connection_type="API")
    await _mk("Draft One", status="draft", connection_type="MCP")
    rows, total = await repo.list_and_count(status="all", connection_type=None, search_text=None)
    assert total == 2 and len(rows) == 2
    rows, total = await repo.list_and_count(status="active", connection_type=None, search_text=None)
    assert total == 1 and rows[0].name == "Active One"
    rows, total = await repo.list_and_count(status="all", connection_type="api", search_text=None)
    assert total == 1 and rows[0].connection_type == "API"          # .upper() applied
    rows, total = await repo.list_and_count(status="all", connection_type=None, search_text="draft")
    assert total == 1 and rows[0].name == "Draft One"


@pytest.mark.asyncio
async def test_increment_calls_is_atomic_and_refreshes(db):
    a = await _mk("Counter", status="active", total_calls=5)
    returned = await repo.increment_calls(a)
    assert returned.total_calls == 6                                # in-memory refreshed
    assert (await repo.by_id(a.id)).total_calls == 6                # persisted
    await repo.increment_calls(a)
    assert (await repo.by_id(a.id)).total_calls == 7


@pytest.mark.asyncio
async def test_save_partial_delete_count(db):
    a = await _mk("S", status="active", rating_up=0)
    a.rating_up = 3
    await repo.save(a, update_fields=["rating_up"])
    assert (await repo.by_id(a.id)).rating_up == 3
    assert await repo.count_all() == 1
    await repo.delete(a)
    assert await repo.by_id(a.id) is None
    assert await repo.count_all() == 0
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd backend && uv run pytest tests/repositories/test_agency_repo.py -v`
Expected: FAIL/ERROR — `app.repositories.agency` does not exist.

- [ ] **Step 3: Implement the repository**

Create `backend/app/repositories/agency.py`:
```python
from __future__ import annotations

from tortoise.expressions import F

from app.models.agency import Agency


async def by_id(agency_id) -> Agency | None:
    return await Agency.get_or_none(id=agency_id)


async def list_and_count(*, status, connection_type, search_text) -> tuple[list[Agency], int]:
    qs = Agency.all()
    if status != "all":
        qs = qs.filter(status=status)
    if connection_type:
        qs = qs.filter(connection_type=connection_type.upper())
    if search_text:
        qs = qs.filter(name__icontains=search_text)
    return await qs, await qs.count()


async def create(**fields) -> Agency:
    return await Agency.create(**fields)


async def save(agency: Agency, *, update_fields: list[str] | None = None) -> None:
    await agency.save(update_fields=update_fields)


async def delete(agency: Agency) -> None:
    await agency.delete()


async def increment_calls(agency: Agency) -> Agency:
    """Atomically add one to total_calls, then refresh the readable value.

    A read-modify-write loses concurrent increments; the atomic SQL update is
    race-safe (matches the Go original).
    """
    await Agency.filter(id=agency.id).update(total_calls=F("total_calls") + 1)
    await agency.refresh_from_db(fields=["total_calls"])
    return agency


async def count_all() -> int:
    return await Agency.all().count()
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd backend && uv run pytest tests/repositories/test_agency_repo.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add backend/app/repositories/agency.py backend/tests/repositories/test_agency_repo.py
git commit -m "feat(repositories): add Agency command repository with atomic increment_calls

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Route Agency command access through the repository

**Files (modify):** `backend/app/services/agency.py`, `backend/app/services/message.py`, `backend/app/services/seed.py`

**Interfaces consumed:** the Task 1 functions. Add `from app.repositories import agency as agency_repo` to each modified file.

- [ ] **Step 1: Refactor `app/services/agency.py`**
  - Imports: remove `from tortoise.exceptions import DoesNotExist` and `from tortoise.expressions import F` (both move to the repo). KEEP `from app.models.agency import Agency` (used in annotations). Keep `ConnectionLog` (out of scope, still used). Add the repo import.
  - `get_agency_or_404`: `try: return await Agency.get(id=agency_id) except DoesNotExist: raise ...` →
    ```python
    agency = await agency_repo.by_id(agency_id)
    if agency is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Agency not found", status=404)
    return agency
    ```
  - `list_agencies`: replace the whole `qs = Agency.all() ... return await qs, await qs.count()` body with:
    ```python
    return await agency_repo.list_and_count(
        status=status_filter, connection_type=connection_type, search_text=search)
    ```
  - `create_agency`: `await Agency.create(**_flatten_agency_payload(body))` → `await agency_repo.create(**_flatten_agency_payload(body))`.
  - `replace_agency`: `await agency.update_from_dict(_flatten_agency_payload(body)).save()` →
    ```python
    agency.update_from_dict(_flatten_agency_payload(body))
    await agency_repo.save(agency)
    ```
  - `update_agency`: `await agency.update_from_dict(update_data).save()` →
    ```python
    agency.update_from_dict(update_data)
    await agency_repo.save(agency)
    ```
  - `delete_agency`: `await agency.delete()` → `await agency_repo.delete(agency)`.
  - `increment_calls`: replace the whole body with `return await agency_repo.increment_calls(agency)`.
  - `update_logo`: `await agency.save(update_fields=["logo", "updated_at"])` → `await agency_repo.save(agency, update_fields=["logo", "updated_at"])`.
  - `run_connection_test`: `await agency.save(update_fields=update_fields)` → `await agency_repo.save(agency, update_fields=update_fields)`. (Leave the `ConnectionLog.create(...)` — out of scope.)

- [ ] **Step 2: Refactor the Agency rating write in `app/services/message.py`**
  Replace the rating fan-out block:
  ```python
      for agency_id in clean_agency_ids(msg.agency_ids):
          try:
              agency = await Agency.get(id=agency_id)
              if msg.rating == "up":
                  agency.rating_up += 1
              elif msg.rating == "down":
                  agency.rating_down += 1
              await agency.save(update_fields=["rating_up", "rating_down"])
          except DoesNotExist:
              continue
  ```
  with:
  ```python
      for agency_id in clean_agency_ids(msg.agency_ids):
          agency = await agency_repo.by_id(agency_id)
          if agency is None:
              continue
          if msg.rating == "up":
              agency.rating_up += 1
          elif msg.rating == "down":
              agency.rating_down += 1
          await agency_repo.save(agency, update_fields=["rating_up", "rating_down"])
  ```
  Add the `agency_repo` import. KEEP `from tortoise.exceptions import DoesNotExist` (still used for the `Message` lookup elsewhere in this file). Drop the `Agency` model import ONLY if it is no longer referenced anywhere in the file after this change (verify — it may still be imported for another use).

- [ ] **Step 3: Refactor `app/services/seed.py` (Agency parts)**
  - `await Agency.all().count()` → `await agency_repo.count_all()`.
  - `await Agency.create(**data)` → `await agency_repo.create(**data)`.
  - Add the `agency_repo` import. Drop the `Agency` model import only if unreferenced afterward. (This file already imports `user_repo` from a prior branch — leave that.)

- [ ] **Step 4: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: PASS, 732 passed / 2 skipped (726 + ~4 repo tests → 730; state the exact number). No FAIL/ERROR.

- [ ] **Step 5: Prove the in-scope Agency command access is ORM-free**

Run: `cd backend && grep -rnE 'Agency\.(get|get_or_none|all|create|filter)|agency\.save\(|agency\.delete\(|update\(total_calls' app/services/agency.py app/services/message.py app/services/seed.py`
Expected: NO matches. (`Agency.filter(...)` for analytics is in OTHER files, out of scope and not grepped here.)

Run: `cd backend && grep -rn 'from tortoise.expressions import F' app/services/agency.py`
Expected: no match (F moved to the repo).

- [ ] **Step 6: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add backend/app/services/agency.py backend/app/services/message.py backend/app/services/seed.py
git commit -m "refactor: route core Agency command access through the repository

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Template extension:** `increment_calls` is the first `increment_*` method — the atomic `F()` counter no longer routes through `save()`, exactly as the spec anticipated.
- **No placeholders:** exact repo code, exact tests (incl. the atomic-increment test), exact per-site mappings for the tricky `update_from_dict`+save and the rating fan-out.
- **Behavior preserved:** `list_and_count` keeps the double-evaluation `(await qs, await qs.count())` and `.upper()`; rating write stays non-atomic; `run_connection_test`'s `ConnectionLog.create` untouched.
- **Scope discipline:** only 3 files; peripheral Agency sites + analytics reads explicitly deferred.
