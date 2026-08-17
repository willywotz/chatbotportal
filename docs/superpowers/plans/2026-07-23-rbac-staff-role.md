# RBAC Staff Role Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the low RBAC tier into a minimal citizen `user` role and a `staff` role (today's `user`, renamed), keeping `admin` unchanged.

**Architecture:** Add a third stored role. The chokepoint (`backend/app/auth/dependencies.py`) gains a `staff` allowlist that equals the basic-user allowlist plus the six read-only ops-dashboard GETs; those six GETs are removed from the basic-user allowlist. The frontend `ROUTE_ROLES` map and `App.tsx` route guards mirror this. A data-only aerich migration rewrites existing `role='user'` rows to `'staff'`. New accounts still default to least-privilege `user`.

**Tech Stack:** Backend — Python 3.12, FastAPI, Tortoise ORM, pydantic, pytest, aerich. Frontend — React 18, TypeScript, React Router, Vitest.

## Global Constraints

- **TDD, no exceptions.** Failing test → confirm fail → minimal code → confirm pass → refactor.
- **Google style guides** for Python / TypeScript. American English naming. No plurals like `xxxList`.
- **Prefix every shell command with `rtk`** (including inside `&&` chains).
- **Roles are exactly:** `user`, `staff`, `admin` (plus anonymous, not stored). `user` ⊂ `staff` ⊂ `admin`.
- **The only delta between `user` and `staff`** is the six read-only dashboard GETs: `/api/v1/dashboard/stats`, `/api/v1/executive-summary`, `/api/v1/agency-health`, `/api/v1/usage-heatmap`, `/api/v1/insight/usage`, `/api/v1/feedback/stats`.
- **`User.role` column is unchanged** — `CharField(max_length=20, default="user")`. No aerich schema change; the migration is data-only.
- **Never hand-carry a *stale* `MODELS_STATE`.** This migration has no model change, so its `MODELS_STATE` is copied verbatim from migration 25 (genuinely current, not stale) — documented in the commit body.
- **The single source of truth for the frontend role type is `frontend/src/features/auth/roles.ts`** (`Role`); `UserRole` in `userApi.ts` is `= Role`.
- Run backend tests from `backend/` with `rtk pytest`; frontend tests from `frontend/` with `rtk vitest run`.

---

## File Structure

**Backend**
- `backend/app/schemas/user.py` — `Role` literal (add `staff`).
- `backend/app/auth/dependencies.py` — chokepoint: rename constant, split basic-user, add staff allowlist, register in `_ROLE_ALLOWLIST`.
- `backend/tests/test_user_schema_roles.py` — rewritten for three roles.
- `backend/tests/test_basic_user_allowlist.py` — rewritten (dashboards now denied for `user`).
- `backend/tests/test_staff_allowlist.py` — **new**, staff allowlist + surface-parity assertions.
- `backend/tests/test_residual_role_denied.py` — extended (residual role now denied on a dashboard too).
- `backend/migrations/models/26_<ts>_promote_user_to_staff.py` — **new**, data-only migration.

**Frontend**
- `frontend/src/features/auth/roles.ts` — `Role` + `ROUTE_ROLES`.
- `frontend/src/features/auth/roles.test.ts` — updated.
- `frontend/src/App.tsx` — route guards.
- `frontend/src/features/users/roleLabels.ts` — add `staff` label + order.
- `frontend/src/features/settings/SettingsLayout.tsx` — `SettingsIndexRedirect` handles `staff`/`user`.
- `frontend/src/features/public/PublicPortal.tsx`, `frontend/src/features/public/InfoPage.tsx` — relabel login control.
- Test updates: `roleLabels.test.ts`, `ProtectedRoute.test.tsx`, `UsersPage.test.tsx`, `SettingsLayout.test.tsx`.

**Docs**
- `CONTEXT.md` — Auth & RBAC section + `User` data-model row.

---

## Task 1: Backend — `Role` literal accepts `staff`

**Files:**
- Modify: `backend/app/schemas/user.py:12`
- Test: `backend/tests/test_user_schema_roles.py`

**Interfaces:**
- Produces: `Role = Literal["user", "staff", "admin"]` consumed by `UserCreate`/`UserUpdate` and the chokepoint's mental model.

- [ ] **Step 1: Rewrite the failing test**

Replace the whole body of `backend/tests/test_user_schema_roles.py` with:

```python
"""The Role literal accepts the three roles and rejects everything else."""
import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate


@pytest.mark.parametrize("role", ["user", "staff", "admin"])
def test_supported_roles_accepted(role):
    assert UserCreate(email="a@x.com", role=role).role == role


@pytest.mark.parametrize("role", ["viewer", "auditor", "agency_owner", "superuser", ""])
def test_unknown_roles_rejected(role):
    with pytest.raises(ValidationError):
        UserCreate(email="a@x.com", role=role)


def test_role_defaults_to_user():
    assert UserCreate(email="a@x.com").role == "user"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/test_user_schema_roles.py -v`
Expected: FAIL — `test_supported_roles_accepted[staff]` raises `ValidationError` (current literal is `["user", "admin"]`).

- [ ] **Step 3: Add `staff` to the literal**

In `backend/app/schemas/user.py`, change line 12:

```python
Role = Literal["user", "staff", "admin"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk pytest tests/test_user_schema_roles.py -v`
Expected: PASS (all parametrizations).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/user.py backend/tests/test_user_schema_roles.py && rtk git commit -m "feat: accept staff role in user schema literal"
```

---

## Task 2: Backend — chokepoint splits `user` from `staff`

**Files:**
- Modify: `backend/app/auth/dependencies.py:54-64` (constant), `:103-113` (`_is_allowed_for_basic_user`), `:213` (`_ROLE_ALLOWLIST`)
- Test: `backend/tests/test_basic_user_allowlist.py`, `backend/tests/test_staff_allowlist.py` (new)

**Interfaces:**
- Consumes: `Role` from Task 1 (conceptually).
- Produces: `_STAFF_GET_EXACT: frozenset[str]`, `_is_allowed_for_staff(method, path) -> bool`, and `_ROLE_ALLOWLIST = {"user": _is_allowed_for_basic_user, "staff": _is_allowed_for_staff}`. `_is_allowed_for_basic_user` no longer grants the six dashboard GETs.

- [ ] **Step 1: Rewrite the basic-user dashboard test to expect denial**

In `backend/tests/test_basic_user_allowlist.py`, replace `test_ops_dashboard_reads_allowed` with:

```python
def test_ops_dashboard_reads_denied_for_basic_user():
    """The six read-only dashboards are now staff-only, not basic-user."""
    assert not _is_allowed_for_basic_user("GET", "/api/v1/dashboard/stats")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/executive-summary")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/agency-health")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/usage-heatmap")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/insight/usage")
    assert not _is_allowed_for_basic_user("GET", "/api/v1/feedback/stats")
```

Leave the rest of the file (chat, rating, agencies-list, conversations, auth, resolve-role tests) unchanged — `user` keeps all of those.

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/test_basic_user_allowlist.py::test_ops_dashboard_reads_denied_for_basic_user -v`
Expected: FAIL — the paths are still allowed (assertion error on the first `assert not`).

- [ ] **Step 3: Split the allowlist in `dependencies.py`**

Rename the constant and its docstring (lines ~54-64):

```python
# Read-only ops dashboards a `staff` role may view: Dashboard, Executive,
# Agency Health, Usage Heatmap, Usage Analytics, Feedback. The write side of
# each page (e.g. POST /executive-summary/regenerate) stays admin-only, and a
# plain `user` cannot reach these at all.
_STAFF_GET_EXACT = frozenset({
    "/api/v1/dashboard/stats",
    "/api/v1/executive-summary",
    "/api/v1/agency-health",
    "/api/v1/usage-heatmap",
    "/api/v1/insight/usage",
    "/api/v1/feedback/stats",
})
```

Remove the dashboard clause from `_is_allowed_for_basic_user` (delete the two lines that reference `_BASIC_USER_GET_EXACT`), leaving:

```python
def _is_allowed_for_basic_user(method: str, path: str) -> bool:
    """A plain ``user`` role: chat + architecture list + own history + shared writes."""
    if _is_shared_write(method, path):
        return True
    if method == "GET" and path == "/api/v1/agencies":  # Architecture page (list only)
        return True
    if method == "GET" and _CONVERSATION_MESSAGES_GET_PATTERN.match(path):
        return True
    return False
```

Add the staff allowlist directly below `_is_allowed_for_basic_user`:

```python
def _is_allowed_for_staff(method: str, path: str) -> bool:
    """Role ``staff``: everything a basic user can do, plus read-only ops dashboards."""
    if _is_allowed_for_basic_user(method, path):
        return True
    return method == "GET" and path in _STAFF_GET_EXACT
```

Update `_ROLE_ALLOWLIST` (line ~213):

```python
_ROLE_ALLOWLIST = {
    "user": _is_allowed_for_basic_user,
    "staff": _is_allowed_for_staff,
}
```

Leave the unknown-role fallback in `enforce_role_allowlist` as `_is_allowed_for_basic_user` (still least-privilege).

- [ ] **Step 4: Write the staff-allowlist test**

Create `backend/tests/test_staff_allowlist.py`:

```python
"""The staff allowlist = basic-user allowlist + the six read-only dashboards."""
from app.auth.dependencies import (
    _STAFF_GET_EXACT,
    _is_allowed_for_basic_user,
    _is_allowed_for_staff,
)

_DASHBOARDS = [
    "/api/v1/dashboard/stats",
    "/api/v1/executive-summary",
    "/api/v1/agency-health",
    "/api/v1/usage-heatmap",
    "/api/v1/insight/usage",
    "/api/v1/feedback/stats",
]


def test_staff_reads_all_six_dashboards():
    for path in _DASHBOARDS:
        assert _is_allowed_for_staff("GET", path)


def test_staff_get_exact_is_exactly_the_six_dashboards():
    assert _STAFF_GET_EXACT == frozenset(_DASHBOARDS)


def test_staff_keeps_everything_a_basic_user_can_do():
    shared = [
        ("POST", "/api/v1/chat"),
        ("POST", "/api/v1/chat/stream"),
        ("POST", "/api/v1/responses"),
        ("PATCH", "/api/v1/messages/abc-123/rating"),
        ("GET", "/api/v1/conversations"),
        ("DELETE", "/api/v1/conversations/abc-123"),
        ("GET", "/api/v1/conversations/abc-123/messages"),
        ("GET", "/api/v1/agencies"),
        ("GET", "/api/v1/auth/me"),
    ]
    for method, path in shared:
        assert _is_allowed_for_basic_user(method, path)
        assert _is_allowed_for_staff(method, path)


def test_staff_still_cannot_reach_admin_surface():
    for method, path in [
        ("GET", "/api/v1/connection-logs"),
        ("GET", "/api/v1/api-keys/"),
        ("POST", "/api/v1/executive-summary/regenerate"),
        ("DELETE", "/api/v1/agencies/abc-123"),
    ]:
        assert not _is_allowed_for_staff(method, path)
```

- [ ] **Step 5: Run both test files to verify they pass**

Run: `rtk pytest tests/test_basic_user_allowlist.py tests/test_staff_allowlist.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/auth/dependencies.py backend/tests/test_basic_user_allowlist.py backend/tests/test_staff_allowlist.py && rtk git commit -m "feat: split staff role from user in the auth chokepoint"
```

---

## Task 3: Backend — surface-parity + residual-role safety net

**Files:**
- Modify: `backend/tests/test_staff_allowlist.py` (add parity test)
- Modify: `backend/tests/test_residual_role_denied.py`

**Interfaces:**
- Consumes: `_is_allowed_for_basic_user`, `_is_allowed_for_staff` (Task 2); `enforce_role_allowlist` (existing).

- [ ] **Step 1: Add the surface-parity test**

Append to `backend/tests/test_staff_allowlist.py`. This is the safety net for "no surviving caller's access changes": `staff` must reach exactly the pre-split `user` set, and the new `user` set is that minus the six dashboards.

```python
# The pre-split `user` reachable surface (representative (method, path) pairs),
# captured from the two-role model. `staff` must reach all of these.
_PRE_SPLIT_USER_SURFACE = [
    ("POST", "/api/v1/chat"),
    ("POST", "/api/v1/chat/stream"),
    ("POST", "/api/v1/responses"),
    ("PATCH", "/api/v1/messages/abc-123/rating"),
    ("GET", "/api/v1/conversations"),
    ("DELETE", "/api/v1/conversations/abc-123"),
    ("GET", "/api/v1/conversations/abc-123/messages"),
    ("GET", "/api/v1/agencies"),
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/dashboard/stats"),
    ("GET", "/api/v1/executive-summary"),
    ("GET", "/api/v1/agency-health"),
    ("GET", "/api/v1/usage-heatmap"),
    ("GET", "/api/v1/insight/usage"),
    ("GET", "/api/v1/feedback/stats"),
]


def test_staff_surface_equals_pre_split_user_surface():
    for method, path in _PRE_SPLIT_USER_SURFACE:
        assert _is_allowed_for_staff(method, path), f"staff lost {method} {path}"


def test_user_surface_is_staff_minus_the_dashboards():
    for method, path in _PRE_SPLIT_USER_SURFACE:
        if (method, path) in [("GET", p) for p in _DASHBOARDS]:
            assert not _is_allowed_for_basic_user(method, path), f"user kept dashboard {path}"
        else:
            assert _is_allowed_for_basic_user(method, path), f"user lost {method} {path}"
```

- [ ] **Step 2: Run the parity test**

Run: `rtk pytest tests/test_staff_allowlist.py -v`
Expected: PASS.

- [ ] **Step 3: Extend the residual-role test**

In `backend/tests/test_residual_role_denied.py`, add a case asserting an unknown residual role is now also denied on a dashboard (it falls back to basic-user, which no longer grants dashboards):

```python
async def test_residual_viewer_denied_on_dashboard(db):
    token = await _token_for_viewer()
    with pytest.raises(HTTPException) as e:
        await enforce_role_allowlist(
            _request("GET", "/api/v1/dashboard/stats"), _creds(token)
        )
    assert e.value.status_code == 403
```

- [ ] **Step 4: Run the residual-role test**

Run: `rtk pytest tests/test_residual_role_denied.py -v`
Expected: PASS (existing chat-allowed / api-keys-denied cases plus the new dashboard-denied case).

- [ ] **Step 5: Run the full auth test slice**

Run: `rtk pytest tests/test_basic_user_allowlist.py tests/test_staff_allowlist.py tests/test_residual_role_denied.py tests/test_user_schema_roles.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
rtk git add backend/tests/test_staff_allowlist.py backend/tests/test_residual_role_denied.py && rtk git commit -m "test: surface-parity and residual-role safety net for staff split"
```

---

## Task 4: Backend — data-only migration promoting `user` to `staff`

**Files:**
- Create: `backend/migrations/models/26_<timestamp>_promote_user_to_staff.py`

**Interfaces:**
- Consumes: nothing in code — a DB migration. The next migration number is **26** (latest is `25_20260723074134_drop_rate_limit_columns.py`).

> **Why hand-written:** the `User.role` column does not change, so `aerich migrate` detects no schema delta and generates nothing. This is a data-only migration. Per `docs/aerich-migrations.md`, hand-author the file. Because the models are unchanged, copy the `MODELS_STATE = (...)` block **verbatim** from migration 25 — it is genuinely current, not stale.

- [ ] **Step 1: Confirm the next number and get a timestamp**

Run: `rtk ls backend/migrations/models/ | sort -t_ -k1 -n | tail -1`
Expected: `25_20260723074134_drop_rate_limit_columns.py` — so the new file is `26_...`. Use any monotonic `YYYYMMDDHHMMSS` after `20260723074134` for `<timestamp>` (e.g. today's date-time).

- [ ] **Step 2: Create the migration file**

Create `backend/migrations/models/26_<timestamp>_promote_user_to_staff.py`:

```python
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    # Data-only migration. Existing `user` accounts are the pre-split
    # staff/officers, so promote them to the renamed `staff` role. `admin` is
    # untouched. New accounts continue to default to the minimal `user` role.
    #
    # IRREVERSIBLE for role identity: after this runs there is no way to tell a
    # migrated officer from an account that was already `staff`, so downgrade
    # cannot restore the prior distribution and is a deliberate no-op.
    return """
        UPDATE "users" SET "role" = 'staff' WHERE "role" = 'user';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return ""
```

Then append, **copied verbatim from migration 25**, the entire `MODELS_STATE = (` … `)` block (the multi-line base64 literal). Do not edit or regenerate it — the models are unchanged.

- [ ] **Step 3: Apply the migration against the dev DB**

Run: `cd backend && rtk proxy .venv/bin/aerich upgrade`
Expected: `Success upgrade 26_<timestamp>_promote_user_to_staff`. (Use `rtk proxy` so aerich's output isn't filtered.)

- [ ] **Step 4: Verify no existing migration file was rewritten**

Run: `rtk git status --short backend/migrations/`
Expected: exactly ONE new untracked file (the `26_...` file); nothing modified or deleted. If any existing migration changed, `rtk git checkout` to restore it and investigate before continuing (see `docs/aerich-migrations.md` checklist item 1).

- [ ] **Step 5: Verify the data change**

Run: `rtk proxy psql "$DATABASE_URL" -c "SELECT role, count(*) FROM users GROUP BY role ORDER BY role;"`
Expected: no rows with `role = 'user'` remain on the dev DB if any existed before; former `user` rows now counted under `staff`; `admin` count unchanged.

- [ ] **Step 6: Commit**

```bash
rtk git add backend/migrations/models/26_*_promote_user_to_staff.py && rtk git commit -m "feat: migrate existing user accounts to staff role

Data-only migration; User.role column unchanged, so MODELS_STATE is copied
verbatim from migration 25 (models unchanged). Irreversible for role identity."
```

---

## Task 5: Frontend — `roles.ts` role type and route map

**Files:**
- Modify: `frontend/src/features/auth/roles.ts`
- Test: `frontend/src/features/auth/roles.test.ts`

**Interfaces:**
- Produces: `Role = "user" | "staff" | "admin"`; `ROUTE_ROLES` with `/chat`, `/architecture`, `/history` open to all three roles, the six dashboards + `/settings` + `/settings/usage` + `/usage` open to `["staff","admin"]`, everything else `["admin"]`; `canAccess(role, path)` unchanged in signature.

- [ ] **Step 1: Update `roles.test.ts` for the three-role model**

Open `frontend/src/features/auth/roles.test.ts` and set expectations:
- `canAccess("user", "/chat")` → true; `canAccess("user", "/architecture")` → true; `canAccess("user", "/history")` → true.
- `canAccess("user", "/dashboard")` → false; `canAccess("user", "/settings/usage")` → false.
- `canAccess("staff", "/dashboard")` → true; `canAccess("staff", "/settings/usage")` → true; `canAccess("staff", "/users")` → false.
- `canAccess("admin", "/users")` → true.

Add these assertions (adapt to the file's existing structure; keep any existing admin/unknown-path cases):

```ts
import { describe, expect, it } from "vitest";
import { canAccess } from "./roles";

describe("canAccess", () => {
  it("lets a user reach chat, architecture, and history", () => {
    for (const path of ["/chat", "/architecture", "/history"]) {
      expect(canAccess("user", path)).toBe(true);
    }
  });

  it("keeps ops dashboards and settings away from a plain user", () => {
    for (const path of ["/dashboard", "/executive", "/health", "/heatmap", "/feedback", "/settings", "/settings/usage"]) {
      expect(canAccess("user", path)).toBe(false);
    }
  });

  it("gives staff the dashboards but not admin pages", () => {
    for (const path of ["/dashboard", "/executive", "/health", "/heatmap", "/feedback", "/settings/usage"]) {
      expect(canAccess("staff", path)).toBe(true);
    }
    expect(canAccess("staff", "/users")).toBe(false);
    expect(canAccess("staff", "/agencies")).toBe(false);
  });

  it("gives admin everything", () => {
    expect(canAccess("admin", "/users")).toBe(true);
    expect(canAccess("admin", "/dashboard")).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk vitest run src/features/auth/roles.test.ts`
Expected: FAIL — `canAccess("user", "/dashboard")` is currently `true` (route is `ALL`).

- [ ] **Step 3: Update `roles.ts`**

Replace the top of `frontend/src/features/auth/roles.ts`:

```ts
export type Role = "user" | "staff" | "admin";

const ALL: Role[] = ["user", "staff", "admin"];
const STAFF: Role[] = ["staff", "admin"];
const ADMIN: Role[] = ["admin"];
```

Update `ROUTE_ROLES` entries (leave `canAccess` unchanged):

```ts
export const ROUTE_ROLES: Record<string, Role[]> = {
  "/chat": ALL,
  "/architecture": ALL,
  "/history": ALL,
  "/dashboard": STAFF,
  "/executive": STAFF,
  "/health": STAFF,
  "/heatmap": STAFF,
  "/usage": STAFF,
  "/feedback": STAFF,
  "/agencies": ADMIN,
  "/agencies/:id": ADMIN,
  "/agencies/new": ADMIN,
  "/agencies/:id/setup": ADMIN,
  "/connection-logs": ADMIN,
  "/api-keys": ADMIN,
  "/users": ADMIN,
  "/audit-log": ADMIN,
  "/settings": STAFF,
  "/settings/system": ADMIN,
  "/settings/llm": ADMIN,
  "/settings/api-keys": ADMIN,
  "/settings/users": ADMIN,
  "/settings/usage": STAFF,
  "/settings/connections": ADMIN,
  "/settings/audit": ADMIN,
  "/llm-settings": ADMIN,
  "/popular-questions": ADMIN,
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk vitest run src/features/auth/roles.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/features/auth/roles.ts frontend/src/features/auth/roles.test.ts && rtk git commit -m "feat: add staff tier to frontend route role map"
```

---

## Task 6: Frontend — `App.tsx` route guards and Settings redirect

**Files:**
- Modify: `frontend/src/App.tsx:78-110`
- Modify: `frontend/src/features/settings/SettingsLayout.tsx:23-25`
- Test: `frontend/src/features/settings/SettingsLayout.test.tsx`

**Interfaces:**
- Consumes: `ProtectedRoute` (`allowedRoles?: Role[]`, `requireAdmin?`), `Role` from Task 5.
- Produces: dashboard routes wrapped in `allowedRoles={["staff", "admin"]}`; `/chat`, `/architecture`, `/history` open to any authenticated role; `/settings/usage` guarded to staff+admin; `SettingsIndexRedirect` routes `user` away.

- [ ] **Step 1: Update the Settings redirect test**

In `frontend/src/features/settings/SettingsLayout.test.tsx`, add/adjust cases for the three roles. `SettingsIndexRedirect` should send `admin` → `/settings/system`, `staff` → `/settings/usage`, and `user` → `/chat` (a user has no settings tab). Follow the file's existing render/mocking pattern for `useAuth`; assert the resulting `<Navigate>` target for each role.

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk vitest run src/features/settings/SettingsLayout.test.tsx`
Expected: FAIL — the current redirect only branches on `isAdmin` (non-admin → `/settings/usage`), so the `user` → `/chat` case fails.

- [ ] **Step 3: Update `SettingsIndexRedirect`**

In `frontend/src/features/settings/SettingsLayout.tsx`, replace `SettingsIndexRedirect`:

```tsx
export function SettingsIndexRedirect() {
  const { user } = useAuth();
  if (user?.role === "admin") return <Navigate to="/settings/system" replace />;
  if (user?.role === "staff") return <Navigate to="/settings/usage" replace />;
  return <Navigate to="/chat" replace />;
}
```

- [ ] **Step 4: Update `App.tsx` route guards**

In `frontend/src/App.tsx`, inside the authenticated `AppLayout` group (lines ~78-110): keep `/chat`, `/architecture`, `/history` directly under the outer `ProtectedRoute`. Wrap the six dashboard routes in a staff+admin group, and guard the settings usage tab. Replace the dashboard block:

```tsx
{/* Every authenticated role */}
<Route path="/chat" element={<ChatPage />} />
<Route path="/architecture" element={<ArchitecturePage />} />
{/* Own conversation history — the API scopes non-admins to their own rows. */}
<Route path="/history" element={<HistoryPage />} />

{/* staff + admin: read-only ops dashboards */}
<Route element={<ProtectedRoute allowedRoles={["staff", "admin"]}><Outlet /></ProtectedRoute>}>
  <Route path="/dashboard" element={<DashboardPage />} />
  <Route path="/executive" element={<ExecutivePage />} />
  <Route path="/health" element={<HealthPage />} />
  <Route path="/heatmap" element={<HeatmapPage />} />
  <Route path="/feedback" element={<FeedbackPage />} />
</Route>
```

In the Settings nested block, guard the usage tab (it is the Usage Analytics dashboard):

```tsx
<Route path="usage" element={<ProtectedRoute allowedRoles={["staff", "admin"]}><UsageAnalyticsPage /></ProtectedRoute>} />
```

Leave the admin-only agencies group, the `requireAdmin` settings tabs, the redirect routes, and `/popular-questions` unchanged.

- [ ] **Step 5: Run test to verify it passes**

Run: `rtk vitest run src/features/settings/SettingsLayout.test.tsx`
Expected: PASS.

- [ ] **Step 6: Typecheck the frontend**

Run: `cd frontend && rtk tsc --noEmit`
Expected: no errors (the `Role` union widened; `allowedRoles={["staff","admin"]}` is valid).

- [ ] **Step 7: Commit**

```bash
rtk git add frontend/src/App.tsx frontend/src/features/settings/SettingsLayout.tsx frontend/src/features/settings/SettingsLayout.test.tsx && rtk git commit -m "feat: gate ops dashboards to staff+admin in routing"
```

---

## Task 7: Frontend — role labels and dependent tests

**Files:**
- Modify: `frontend/src/features/users/roleLabels.ts`
- Test: `frontend/src/features/users/roleLabels.test.ts`, `frontend/src/features/auth/ProtectedRoute.test.tsx`, `frontend/src/features/users/UsersPage.test.tsx`

**Interfaces:**
- Consumes: `Role`/`UserRole` from Task 5.
- Produces: `ROLE_LABEL` with a `staff` entry; `ROLE_ORDER = ["user", "staff", "admin"]`. `UserFormDialog` dropdown and `UsersPage` filter read these, so both update for free.

- [ ] **Step 1: Update `roleLabels.test.ts`**

Assert all three labels and the order:

```ts
import { describe, expect, it } from "vitest";
import { ROLE_LABEL, ROLE_ORDER } from "./roleLabels";

describe("role labels", () => {
  it("labels all three roles in Thai", () => {
    expect(ROLE_LABEL.user).toBe("ผู้ใช้");
    expect(ROLE_LABEL.staff).toBe("เจ้าหน้าที่");
    expect(ROLE_LABEL.admin).toBe("ผู้ดูแลระบบ");
  });

  it("orders roles least- to most-privileged", () => {
    expect(ROLE_ORDER).toEqual(["user", "staff", "admin"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk vitest run src/features/users/roleLabels.test.ts`
Expected: FAIL — `ROLE_LABEL.staff` is `undefined`.

- [ ] **Step 3: Update `roleLabels.ts`**

```ts
import type { UserRole } from "./userApi";

/** Short Thai labels for each role — used by the users table badge and role filter. */
export const ROLE_LABEL: Record<UserRole, string> = {
  user: "ผู้ใช้",
  staff: "เจ้าหน้าที่",
  admin: "ผู้ดูแลระบบ",
};

/** Roles ordered from least to most privileged, for stable dropdown ordering. */
export const ROLE_ORDER: UserRole[] = ["user", "staff", "admin"];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk vitest run src/features/users/roleLabels.test.ts`
Expected: PASS.

- [ ] **Step 5: Update `ProtectedRoute.test.tsx` and `UsersPage.test.tsx` for three roles**

- `ProtectedRoute.test.tsx`: add a case that a `staff` user hitting an `allowedRoles={["staff","admin"]}` route renders children, and a `user` hitting it is redirected to `/chat`. Keep existing admin/`requireAdmin` cases.
- `UsersPage.test.tsx`: wherever the role filter or badge expects a fixed role set, include `staff`. If a test enumerates the filter options, expect three (`user`, `staff`, `admin`).

Follow each file's existing mocking pattern (they mock `useAuth`/`userApi`); do not restructure them.

- [ ] **Step 6: Run the affected frontend tests**

Run: `rtk vitest run src/features/users src/features/auth`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
rtk git add frontend/src/features/users/roleLabels.ts frontend/src/features/users/roleLabels.test.ts frontend/src/features/auth/ProtectedRoute.test.tsx frontend/src/features/users/UsersPage.test.tsx && rtk git commit -m "feat: add staff role label and update role-dependent tests"
```

---

## Task 8: Frontend — relabel the public login control

**Files:**
- Modify: `frontend/src/features/public/PublicPortal.tsx:40`
- Modify: `frontend/src/features/public/InfoPage.tsx:19`

**Interfaces:** none — copy change only. (The `frontend/dist/` occurrences are build output and regenerate; do not edit them.)

- [ ] **Step 1: Change the label in both files**

In each file, change the login control text from `เข้าสู่ระบบเจ้าหน้าที่` to `เข้าสู่ระบบ` (leave the `<ArrowRight … />` icon and surrounding markup unchanged). The now serves citizens as well as staff.

- [ ] **Step 2: Verify no source occurrence of the old label remains**

Run: `rtk grep -n "เข้าสู่ระบบเจ้าหน้าที่" frontend/src/`
Expected: no matches (only `frontend/dist/` build artifacts may still contain it until the next build).

- [ ] **Step 3: Commit**

```bash
rtk git add frontend/src/features/public/PublicPortal.tsx frontend/src/features/public/InfoPage.tsx && rtk git commit -m "feat: relabel public login control to serve all users"
```

---

## Task 9: Full test sweep + docs

**Files:**
- Modify: `CONTEXT.md`

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && rtk pytest`
Expected: PASS (no regressions from the role split).

- [ ] **Step 2: Run the full frontend suite + typecheck**

Run: `cd frontend && rtk vitest run && rtk tsc --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 3: Update `CONTEXT.md`**

In the **Auth & RBAC** section, change the roles description to three roles:
- `user` (citizen): chat, own conversation history, and the Architecture list. No ops dashboards.
- `staff`: everything `user` has plus **read-only** Dashboard · Executive · Agency Health · Usage Heatmap · Usage Analytics · Feedback.
- `admin` (full), plus anonymous.

Update the chokepoint prose: `_ROLE_ALLOWLIST` now has `user` → `_is_allowed_for_basic_user` and `staff` → `_is_allowed_for_staff` (= basic-user + `_STAFF_GET_EXACT`); the unknown-role fallback stays basic-user (least-privilege). Note that public self-registration for `user` is a planned follow-up (see `docs/superpowers/specs/2026-07-23-rbac-staff-role-design.md`).

In the **data model** table, change the `User` row: `role` = `user|staff|admin`.

- [ ] **Step 4: Commit**

```bash
rtk git add CONTEXT.md && rtk git commit -m "docs: describe three-role RBAC (user/staff/admin) in CONTEXT.md"
```

---

## Self-Review Notes (author checklist, already applied)

- **Spec coverage:** Role model → Tasks 1,2. Invariant/parity → Tasks 2,3. Chokepoint → Task 2. Schema → Task 1. Migration → Task 4. Frontend `roles.ts`/`App.tsx`/`roleLabels.ts`/`SettingsIndexRedirect`/sidebar (auto via `canAccess`) → Tasks 5,6,7. Login relabel → Task 8. Docs → Task 9. No new `require_staff` (spec: not needed) — confirmed the six dashboard endpoints carry no `require_admin`.
- **Type consistency:** `_STAFF_GET_EXACT`, `_is_allowed_for_staff`, `_ROLE_ALLOWLIST` names identical across Tasks 2–3. `Role`/`STAFF`/`ROUTE_ROLES` identical across Tasks 5–7. `SettingsIndexRedirect` signature unchanged.
- **No placeholders:** every code step shows full code; every run step shows the command and expected result.
```
