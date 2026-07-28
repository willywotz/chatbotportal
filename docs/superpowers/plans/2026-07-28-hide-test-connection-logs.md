# Hide test-action connection logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide `action="test"` connection logs by default on `/settings/connections`, with a toggle to reveal them, filtered in the backend query.

**Architecture:** A boolean `include_test` flag (default `false`) flows from a filter-bar pill toggle → `useConnectionLogs`/`useConnectionLogInfo` → the `/connection-logs` and `/connection-logs/info` endpoints. When `false`, the backend applies `.exclude(action="test")` to the base queryset before all filters, pagination, and stat aggregates.

**Tech Stack:** FastAPI + Tortoise ORM (backend, pytest/httpx), React + React Query + MSW (frontend, vitest).

## Global Constraints

- TDD mandatory: failing test → confirm fail → minimal code → confirm pass.
- No model or migration changes — `ConnectionLog.action` already exists (`test | query`).
- Backend filter must run in the DB query, not in Python post-processing.
- `include_test=false` (or absent) is the default everywhere.
- American English identifiers; Thai UI copy matches existing strings.

---

### Task 1: Backend `include_test` filter on list + info endpoints

**Files:**
- Modify: `backend/app/routers/connection_logs.py` (`list_connection_logs`, `get_connection_log_info`)
- Modify: `backend/tests/test_connection_logs_filter.py` (patch 3 existing tests that seed `action="test"`)
- Test: `backend/tests/test_connection_logs_test_action_filter.py` (new)

**Interfaces:**
- Produces: `GET /api/v1/connection-logs?include_test=<bool>` and `GET /api/v1/connection-logs/info?include_test=<bool>`. Default `false` → response omits `action="test"` rows and their contribution to `total_items`, `total_connections`, `successful_connections`, `failed_connections`, `average_latency_ms`.

- [ ] **Step 1: Patch existing tests that rely on test-action logs being visible**

The three tests in `test_connection_logs_filter.py` seed `action="test"` and expect them counted. Add `"include_test": True` to each request so they keep characterizing pagination/alias/status behavior against all logs.

In `test_connection_logs_paginate_unchanged`:
```python
        r = await c.get("/api/v1/connection-logs", params={"page": 1, "limit": 2, "include_test": True})
```
In `test_status_and_type_filters_apply_to_items_and_stats`:
```python
        r = await c.get("/api/v1/connection-logs",
                        params={"status": "success", "connection_type": "API", "include_test": True})
```
In `test_page_size_alias_for_limit`:
```python
        r = await c.get("/api/v1/connection-logs", params={"page_size": 2, "include_test": True})
```

- [ ] **Step 2: Write the failing tests for the new default-exclude behavior**

Create `backend/tests/test_connection_logs_test_action_filter.py`:
```python
"""Test-action visibility on GET /connection-logs and /info."""
import uuid

import pytest

from app.auth.dependencies import get_current_user
from app.main import app
from app.models import Agency, ConnectionLog
from app.models.user import User
from httpx import ASGITransport, AsyncClient


def _admin():
    return User(id=uuid.uuid4(), email="a@x.io", role="admin", is_admin=True)


async def _client():
    app.dependency_overrides[get_current_user] = _admin
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _seed_one_each(ag):
    await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="test")
    await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="query")


@pytest.mark.usefixtures("db")
async def test_test_action_hidden_by_default():
    ag = await Agency.create(name="A", status="active")
    await _seed_one_each(ag)
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs")
    app.dependency_overrides.clear()
    body = r.json()
    assert [i["action"] for i in body["items"]] == ["query"]
    assert body["total_items"] == 1
    assert body["total_connections"] == 1
    assert body["successful_connections"] == 1


@pytest.mark.usefixtures("db")
async def test_include_test_shows_all():
    ag = await Agency.create(name="A", status="active")
    await _seed_one_each(ag)
    async with await _client() as c:
        r = await c.get("/api/v1/connection-logs", params={"include_test": True})
    app.dependency_overrides.clear()
    body = r.json()
    assert body["total_items"] == 2
    assert body["total_connections"] == 2
    assert {i["action"] for i in body["items"]} == {"test", "query"}


@pytest.mark.usefixtures("db")
async def test_info_excludes_test_by_default():
    ag = await Agency.create(name="A", status="active")
    await _seed_one_each(ag)
    async with await _client() as c:
        default = (await c.get("/api/v1/connection-logs/info")).json()
        with_test = (await c.get("/api/v1/connection-logs/info", params={"include_test": True})).json()
    app.dependency_overrides.clear()
    assert default["total_connections"] == 1
    assert with_test["total_connections"] == 2
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `rtk pytest backend/tests/test_connection_logs_test_action_filter.py -v`
Expected: FAIL — default currently returns 2 items / `total_connections == 2` (test logs not excluded).

- [ ] **Step 4: Add the `include_test` param + exclude to `list_connection_logs`**

In `backend/app/routers/connection_logs.py`, add the parameter (place it right after `connection_type`):
```python
    connection_type: str | None = Query(None, description="MCP | API | A2A"),
    include_test: bool = Query(False, description="Include action=test logs"),
    page: int = Query(1, ge=1),
```
Then apply the exclude immediately after building the base queryset:
```python
    qs = ConnectionLog.all()
    if not include_test:
        qs = qs.exclude(action="test")

    start = time.time()
```

- [ ] **Step 5: Add the same param + exclude to `get_connection_log_info`**

```python
@router.get("/info", summary="Get connection log info", response_model=ConnectionLogInfoResponse)
async def get_connection_log_info(
    include_test: bool = Query(False, description="Include action=test logs"),
    user: User = Depends(get_current_user),
) -> ConnectionLogInfoResponse:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    qs = ConnectionLog.all()
    if not include_test:
        qs = qs.exclude(action="test")
```

- [ ] **Step 6: Run the full connection-logs test suite to verify all pass**

Run: `rtk pytest backend/tests/test_connection_logs_test_action_filter.py backend/tests/test_connection_logs_filter.py backend/tests/test_connection_logs_authz.py -v`
Expected: PASS (new default-exclude + include tests pass; patched existing tests still pass).

- [ ] **Step 7: Commit**

```bash
rtk git add backend/app/routers/connection_logs.py backend/tests/test_connection_logs_test_action_filter.py backend/tests/test_connection_logs_filter.py
rtk git commit -m "feat(be): hide action=test connection logs unless include_test=true

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Frontend toggle + hook plumbing

**Files:**
- Modify: `frontend/src/features/connection-logs/useConnectionLogs.ts`
- Modify: `frontend/src/features/connection-logs/ConnectionLogsPage.tsx`
- Modify: `frontend/src/features/connection-logs/ConnectionLogFilters.tsx`
- Test: `frontend/src/features/connection-logs/ConnectionLogsTable.test.tsx` (add a case)

**Interfaces:**
- Consumes: `GET /api/v1/connection-logs?include_test=true` and `/info?include_test=true` from Task 1.
- Produces: filter-bar pill button labeled `แสดงการทดสอบ`; when active the page requests `include_test=true`. `ConnectionLogParams` gains `includeTest?: boolean`; `useConnectionLogInfo(includeTest?: boolean)`.

- [ ] **Step 1: Write the failing frontend test**

Add to `frontend/src/features/connection-logs/ConnectionLogsTable.test.tsx` (a new `describe` block at the end):
```tsx
describe("ConnectionLogs test-action toggle", () => {
  it("omits include_test by default and requests include_test=true when toggled", async () => {
    const urls: string[] = [];
    server.use(
      http.get("*/api/v1/connection-logs", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(EMPTY_LOGS);
      }),
      http.get("*/api/v1/connection-logs/info", () => HttpResponse.json({})),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("ไม่พบข้อมูล")).toBeInTheDocument());
    expect(urls.every((u) => !u.includes("include_test=true"))).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "แสดงการทดสอบ" }));
    await waitFor(() =>
      expect(urls.some((u) => u.includes("include_test=true"))).toBe(true),
    );
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk vitest run frontend/src/features/connection-logs/ConnectionLogsTable.test.tsx`
Expected: FAIL — no button named `แสดงการทดสอบ` exists yet.

- [ ] **Step 3: Thread `includeTest` through the hooks**

In `useConnectionLogs.ts`:
```typescript
export interface ConnectionLogParams {
  page?: number;
  limit?: number;
  search?: string;
  agencyId?: string;
  status?: string;
  connectionType?: string;
  includeTest?: boolean;
}
```
In `fetchConnectionLogs`, after the `connection_type` line:
```typescript
  if (params.connectionType) qs.set('connection_type', params.connectionType);
  if (params.includeTest) qs.set('include_test', 'true');
```
In `useConnectionLogs`, extend the query key:
```typescript
    queryKey: ['connection-logs', params.agencyId ?? null, params.page ?? null, params.limit ?? null, params.search ?? null, params.status ?? null, params.connectionType ?? null, params.includeTest ?? false],
```
Update the info hook + fetcher:
```typescript
async function fetchConnectionLogInfo(includeTest?: boolean): Promise<ConnectionLogInfo> {
  const query = includeTest ? '?include_test=true' : '';
  return await api.get<ConnectionLogInfo>(`/api/v1/connection-logs/info${query}`);
}

export function useConnectionLogInfo(includeTest?: boolean) {
  return useQuery({
    queryKey: ['connection-log-info', includeTest ?? false],
    queryFn: () => fetchConnectionLogInfo(includeTest),
    refetchInterval: REFETCH.normal,
  });
}
```

- [ ] **Step 4: Wire state into `ConnectionLogsPage.tsx`**

Add state near the other filters:
```tsx
  const [includeTest, setIncludeTest] = useState(false);
```
Pass it to both hooks:
```tsx
  const { data: logInfo } = useConnectionLogInfo(includeTest);
  const { data, isLoading, isFetching, isError, refetch } = useConnectionLogs({
    page,
    limit: PAGE_SIZE,
    search: search || undefined,
    agencyId: filterAgency || undefined,
    status: filterStatus || undefined,
    connectionType: filterType || undefined,
    includeTest: includeTest || undefined,
  });
```
Fold the toggle into `hasFilters` and `resetFilters`:
```tsx
  const hasFilters = !!(filterStatus || filterType || filterAgency || search || includeTest);

  const resetFilters = () => {
    setFilterStatus(null);
    setFilterType(null);
    setFilterAgency(null);
    setSearch("");
    setIncludeTest(false);
    setPage(1);
  };
```
Pass the new props to `ConnectionLogFilters` (add to the existing JSX props):
```tsx
        includeTest={includeTest}
        onIncludeTestChange={(v) => { setIncludeTest(v); setPage(1); }}
```

- [ ] **Step 5: Render the toggle in `ConnectionLogFilters.tsx`**

Add to `Props`:
```tsx
  includeTest: boolean;
  onIncludeTestChange: (v: boolean) => void;
```
Add to the destructured params:
```tsx
  onSearchChange, onStatusChange, onTypeChange, onAgencyChange, onReset,
  includeTest, onIncludeTestChange,
```
Add the pill after the MCP/API/A2A `<div className="flex gap-1">` block:
```tsx
      <button
        onClick={() => onIncludeTestChange(!includeTest)}
        className={cn(
          "text-xs px-3 py-1.5 rounded-full border transition-colors",
          includeTest ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:bg-accent"
        )}
      >
        แสดงการทดสอบ
      </button>
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `rtk vitest run frontend/src/features/connection-logs/ConnectionLogsTable.test.tsx`
Expected: PASS.

- [ ] **Step 7: Typecheck + lint**

Run: `rtk tsc` and `rtk lint` in `frontend/`.
Expected: no errors in the modified files.

- [ ] **Step 8: Commit**

```bash
rtk git add frontend/src/features/connection-logs/
rtk git commit -m "feat(fe): toggle to reveal test-action connection logs (backend-filtered)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** default-exclude on list (Task 1 S4) ✓; info endpoint (Task 1 S5) ✓; stats respect filter (Task 1 S2 assertions) ✓; hook `includeTest` + query keys (Task 2 S3) ✓; page state + reset + hasFilters (Task 2 S4) ✓; filter pill `แสดงการทดสอบ` (Task 2 S5) ✓; existing tests patched (Task 1 S1) ✓.
- **Placeholder scan:** none — all steps carry concrete code.
- **Type consistency:** `include_test` (backend snake_case) / `includeTest` (frontend camelCase) used consistently; `onIncludeTestChange` matches between page and filters.

## Out of scope

- No change to `connection_type` / status pills.
- No new `action` values, model, or migration changes.
