# Hide test-action connection logs by default

**Date:** 2026-07-28
**Feature branch:** `feat/hide-test-connection-logs`

## Problem

The `/settings/connections` page (`ConnectionLogsPage`) lists every `ConnectionLog`
row, including automated `action="test"` health-check entries. These dominate the
list and skew the stat tiles. Admins want the test entries hidden by default, with a
button to reveal them. The filtering must happen in the backend query, not by
discarding rows in the browser.

## Behavior

A single boolean flag `include_test`, default `false`.

- **`false` (default):** exclude `action="test"` rows — show only `query` logs.
- **`true`:** show everything (test + query).

The flag governs the list items, the paginated `total_items`, the aggregate stats
(`total_connections`, `successful_connections`, `failed_connections`,
`average_latency_ms`), and the `/info` endpoint, so the stat tiles always match the
visible table.

## Backend — `backend/app/routers/connection_logs.py`

### `list_connection_logs`
- Add `include_test: bool = Query(False, description="Include action=test logs")`.
- Immediately after `qs = ConnectionLog.all()`, apply:
  ```python
  if not include_test:
      qs = qs.exclude(action="test")
  ```
  This runs **before** the search, agency, status, type filters and before the
  `total_connections` / `successful` / `failed` / `average_latency_ms` aggregates,
  so every count derives from the test-filtered queryset.

### `get_connection_log_info`
- Add the same `include_test: bool = Query(False)` param and the same
  `qs.exclude(action="test")` guard after `qs = ConnectionLog.all()`.

No model or migration changes — `action` already exists (`test | query`).

## Frontend

### `useConnectionLogs.ts`
- `ConnectionLogParams`: add `includeTest?: boolean`.
- `fetchConnectionLogs`: `if (params.includeTest) qs.set('include_test', 'true')`.
- `useConnectionLogs` query key: append `params.includeTest ?? false`.
- `fetchConnectionLogInfo(includeTest?: boolean)` forwards `include_test=true`.
- `useConnectionLogInfo(includeTest?: boolean)`: pass through and add to its query key.

### `ConnectionLogsPage.tsx`
- `const [includeTest, setIncludeTest] = useState(false)`.
- Pass `includeTest` to `useConnectionLogs` and `useConnectionLogInfo`.
- `resetFilters` also sets `setIncludeTest(false)`.
- `hasFilters` also true when `includeTest` is on (so the reset button shows and the
  toggle participates in "ล้างตัวกรอง").
- Pass `includeTest` + `onIncludeTestChange` down to `ConnectionLogFilters`.

### `ConnectionLogFilters.tsx`
- New props: `includeTest: boolean`, `onIncludeTestChange: (v: boolean) => void`.
- Render a pill toggle labeled **"แสดงการทดสอบ"** beside the MCP/API/A2A pills,
  styled identically (active = `bg-primary text-primary-foreground border-primary`).
- Clicking flips `includeTest` and resets to page 1 (handled by the page's change
  wrapper, matching the other filters).

## Tests (TDD — write failing first)

### Backend (pytest)
Seed mixed `test` and `query` logs, then assert:
- Default request omits `action="test"` items and stats count only `query`.
- `?include_test=true` returns both test and query items with full-count stats.
- `/info` default excludes test from its counts; `?include_test=true` includes them.

### Frontend (vitest)
- `ConnectionLogFilters` renders the "แสดงการทดสอบ" toggle and calls
  `onIncludeTestChange(true)` when clicked while off.
- Reset (`onReset`) turns the toggle back off (covered via page-level wiring or a
  filters-level assertion that the active class clears when `includeTest=false`).

## Out of scope

- No change to `connection_type` (MCP/API/A2A) or status pills.
- No new `action` values or model/migration changes.
