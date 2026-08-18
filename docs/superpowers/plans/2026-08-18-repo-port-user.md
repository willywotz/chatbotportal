# User Repository Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add `app/repositories/user.py` and route all User *command* access through it, removing Active-Record ORM calls and `DoesNotExist` from the user use-case and the auth data-access sites (which duplicate the same query).

**Architecture:** Second application of the repository template (see spec). Command repository only; no `Protocol`; returns/accepts Tortoise `User` instances. The `active_by_id` query is copy-pasted across `services/user.py`, `auth/dependencies.py` (×2), and `auth/ws.py` — one repo method replaces all of them (root-cause dedup).

**Tech Stack:** Python 3, uv, pytest + pytest-asyncio, Tortoise ORM.

**Spec:** `docs/superpowers/specs/2026-08-18-repository-ports-design.md` (the locked pattern; this plan instantiates it for User).

## Global Constraints

- Test commands: full suite `cd backend && uv run pytest`; one file `cd backend && uv run pytest <path> -v`.
- Behavior-preserving refactor. Baseline: 720 passed / 2 skipped. After Task 1 (+repo tests) expect ~730.
- Branch: `refactor/repo-port-user` (already checked out).
- TDD mandatory. American English. YAGNI — only the methods below.
- **Keep any `User` import still used in type annotations or for other models** (lesson from the Conversation branch — do not drop an import that annotations reference). `auth/dependencies.py` also uses `UserAPIKey` — leave that (different aggregate, later step).
- OUT OF SCOPE: `analytics/usage.py`'s `User.filter(id__in=...)` (read-model), and `UserAPIKey` access.

---

### Task 1: Create the User command repository (TDD)

**Files:**
- Create: `backend/app/repositories/user.py`
- Test: `backend/tests/repositories/test_user_repo.py`

**Interfaces produced:**
```python
async def by_id(user_id) -> User | None
async def active_by_id(user_id) -> User | None
async def active_by_email(email: str) -> User | None
async def email_exists(email: str) -> bool
async def count_other_active_admins(exclude_id) -> int
async def count_all() -> int
async def search(*, search_text: str | None, role, is_active: bool | None) -> list[User]
async def create(**fields) -> User
async def save(user, *, update_fields: list[str] | None = None) -> None
```

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/repositories/test_user_repo.py`:
```python
import pytest

from app.repositories import user as repo


async def _mk(email, **kw):
    return await repo.create(email=email, hashed_password="h", **kw)


@pytest.mark.asyncio
async def test_by_id_present_and_absent(db):
    u = await _mk("a@x.com", role="user")
    assert (await repo.by_id(u.id)).id == u.id
    assert await repo.by_id("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_active_lookups_skip_inactive(db):
    active = await _mk("live@x.com", role="user", is_active=True)
    await _mk("dead@x.com", role="user", is_active=False)
    assert (await repo.active_by_id(active.id)).id == active.id
    assert (await repo.active_by_email("live@x.com")).id == active.id
    assert await repo.active_by_email("dead@x.com") is None


@pytest.mark.asyncio
async def test_email_exists_and_count_all(db):
    await _mk("one@x.com", role="user")
    assert await repo.email_exists("one@x.com") is True
    assert await repo.email_exists("missing@x.com") is False
    assert await repo.count_all() == 1


@pytest.mark.asyncio
async def test_count_other_active_admins_excludes_self(db):
    a1 = await _mk("admin1@x.com", role="admin", is_active=True)
    await _mk("admin2@x.com", role="admin", is_active=True)
    await _mk("inactive-admin@x.com", role="admin", is_active=False)
    assert await repo.count_other_active_admins(a1.id) == 1     # admin2 only


@pytest.mark.asyncio
async def test_search_filters(db):
    await _mk("alice@x.com", role="admin", is_active=True, display_name="Alice")
    await _mk("bob@x.com", role="user", is_active=False, display_name="Bob")
    await _mk("anon@ephemeral.local", role="user", is_active=True, is_ephemeral=True)
    all_rows = await repo.search(search_text=None, role=None, is_active=None)
    assert {u.email for u in all_rows} == {"alice@x.com", "bob@x.com"}   # ephemeral excluded
    admins = await repo.search(search_text=None, role="admin", is_active=None)
    assert [u.email for u in admins] == ["alice@x.com"]
    hits = await repo.search(search_text="ali", role=None, is_active=None)
    assert [u.email for u in hits] == ["alice@x.com"]


@pytest.mark.asyncio
async def test_save_partial(db):
    u = await _mk("s@x.com", role="user", is_active=True)
    u.is_active = False
    await repo.save(u, update_fields=["is_active"])
    assert (await repo.by_id(u.id)).is_active is False
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd backend && uv run pytest tests/repositories/test_user_repo.py -v`
Expected: FAIL/ERROR — `app.repositories.user` does not exist.

- [ ] **Step 3: Implement the repository**

Create `backend/app/repositories/user.py`:
```python
from __future__ import annotations

from tortoise.expressions import Q

from app.models.user import User


async def by_id(user_id) -> User | None:
    return await User.get_or_none(id=user_id)


async def active_by_id(user_id) -> User | None:
    return await User.filter(id=user_id, is_active=True).first()


async def active_by_email(email: str) -> User | None:
    return await User.filter(email=email, is_active=True).first()


async def email_exists(email: str) -> bool:
    return await User.filter(email=email).exists()


async def count_other_active_admins(exclude_id) -> int:
    return await User.filter(role="admin", is_active=True).exclude(id=exclude_id).count()


async def count_all() -> int:
    return await User.all().count()


async def search(*, search_text: str | None, role, is_active: bool | None) -> list[User]:
    qs = User.filter(is_ephemeral=False)
    if search_text:
        qs = qs.filter(Q(email__icontains=search_text) | Q(display_name__icontains=search_text))
    if role:
        qs = qs.filter(role=role)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return await qs.order_by("-created_at")


async def create(**fields) -> User:
    return await User.create(**fields)


async def save(user: User, *, update_fields: list[str] | None = None) -> None:
    await user.save(update_fields=update_fields)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd backend && uv run pytest tests/repositories/test_user_repo.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add backend/app/repositories/user.py backend/tests/repositories/test_user_repo.py
git commit -m "feat(repositories): add User command repository

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Route User command access through the repository

**Files (modify):** `backend/app/services/user.py`, `backend/app/services/seed.py`, `backend/app/auth/dependencies.py`, `backend/app/auth/ws.py`, `backend/app/routers/auth.py`

**Interfaces consumed:** the Task 1 functions. Add `from app.repositories import user as user_repo` to each modified file.

**Rule:** behavior-preserving; read each file, apply the mapping, keep the full suite green. Remove `from tortoise.exceptions import DoesNotExist` and `from tortoise.expressions import Q` from `services/user.py` (they move to the repo) — but KEEP `from app.models.user import User` (still used in annotations). Keep the `User`/`UserAPIKey` imports in the auth/router files (used in annotations and, for `UserAPIKey`, still queried directly — out of scope).

- [ ] **Step 1: Refactor `app/services/user.py`**
  - `ensure_not_last_admin`: `await User.filter(role="admin", is_active=True).exclude(id=target.id).count()` → `await user_repo.count_other_active_admins(target.id)`.
  - `create_user`: `await User.filter(email=data.email).exists()` → `await user_repo.email_exists(data.email)`; `await User.create(...)` → `await user_repo.create(...)` (same kwargs).
  - `list_users`: replace the `qs = User.filter(...)` block with:
    ```python
    is_active = None if status_filter == "all" else (status_filter == "active")
    return await user_repo.search(search_text=search, role=role, is_active=is_active)
    ```
  - `get_user_or_404`: replace the `try: return await User.get(id=user_id) except DoesNotExist: raise ...` with:
    ```python
    user = await user_repo.by_id(user_id)
    if user is None:
        raise ApiError(ErrorCode.NOT_FOUND, "User not found", status=404)
    return user
    ```
  - `apply_update`: `await user.save(update_fields=changed)` → `await user_repo.save(user, update_fields=changed)`.
  - `deactivate`: `await user.save(update_fields=["is_active"])` → `await user_repo.save(user, update_fields=["is_active"])`.
  - `activate`: same as deactivate.
  - `get_active_by_email`: body → `return await user_repo.active_by_email(email)`.
  - `get_active_by_id`: body → `return await user_repo.active_by_id(user_id)`.
  - `create_anonymous`: `await User.create(...)` → `await user_repo.create(...)` (same kwargs).
  - Remove the now-unused `DoesNotExist` and `Q` imports. Keep `User` (annotations).

- [ ] **Step 2: Refactor `app/services/seed.py`**
  - `await User.all().count()` → `await user_repo.count_all()`.
  - `await User.filter(email=DEFAULT_ADMIN["email"]).exists()` → `await user_repo.email_exists(DEFAULT_ADMIN["email"])`.
  - `await User.create(...)` → `await user_repo.create(...)` (same kwargs).
  - Drop the `User` import only if it is no longer referenced anywhere in the file (verify).

- [ ] **Step 3: Refactor `app/auth/dependencies.py`**
  - Replace BOTH `await User.filter(id=..., is_active=True).first()` calls (in `_resolve_api_key` at ~:134 and `_resolve_session_user` at ~:154) with `await user_repo.active_by_id(<the id expr>)` (keep the exact id expression: `api_key.user_id` and `user_id` respectively).
  - Keep `from app.models.user import User, UserAPIKey` (User in annotations; `UserAPIKey.filter(...)` at ~:131 stays — out of scope).

- [ ] **Step 4: Refactor `app/auth/ws.py`**
  - `return await User.filter(id=user_id, is_active=True).first()` → `return await user_repo.active_by_id(user_id)`.
  - Keep the `User` import (used in the `-> User | None` annotation).

- [ ] **Step 5: Refactor `app/routers/auth.py`**
  - `await user.save()` (~:121) → `await user_repo.save(user)`.
  - `await user.save(update_fields=["hashed_password"])` (~:134) → `await user_repo.save(user, update_fields=["hashed_password"])`.
  - Keep the `User` import (annotations).

- [ ] **Step 6: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: PASS, 730 passed / 2 skipped (720 baseline + ~6 repo tests wait — Task 1 added 6 tests → 726). State the exact number from the run; the requirement is no FAIL/ERROR and only the new repo tests added.

- [ ] **Step 7: Prove User command access is ORM-free in the refactored files**

Run: `cd backend && grep -rnE 'User\.(get|get_or_none|filter|create|all|exclude)|user\.save\(' app/services/user.py app/services/seed.py app/auth/dependencies.py app/auth/ws.py app/routers/auth.py`
Expected: NO matches for `User.<orm>` or `user.save(` in these files. (`UserAPIKey.filter` in dependencies.py is a DIFFERENT token and is allowed.)

Run: `cd backend && grep -rn 'DoesNotExist' app/services/user.py`
Expected: no matches.

- [ ] **Step 8: Commit**

```bash
cd /home/foo/nectec/chatbotportal
git add backend/app/services/user.py backend/app/services/seed.py backend/app/auth/dependencies.py backend/app/auth/ws.py backend/app/routers/auth.py
git commit -m "refactor: route User command access through the repository

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** repository surface matches the real call sites; the `active_by_id` dedup (services + auth ×3) is the root-cause fix.
- **No placeholders:** exact repo code, exact tests, exact per-site mappings.
- **Type/name consistency:** `by_id`/`active_by_id`/`active_by_email`/`email_exists`/`count_other_active_admins`/`count_all`/`search`/`create`/`save` used identically in Task 1 and Task 2.
- **Lesson applied:** keep model imports used in annotations (do not repeat the Conversation annotation-import slip).
- **Out of scope preserved:** `analytics/usage.py` `id__in`, `UserAPIKey` access.
