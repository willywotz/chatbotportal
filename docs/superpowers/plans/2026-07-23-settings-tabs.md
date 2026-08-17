# Tabbed Settings Area Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge six separate admin pages (System Settings, LLM, API Keys, Usage, Connection logs, Audit log) into one tabbed Settings area with deep-linkable nested routes, a role-filtered tab bar, and redirects from the old URLs.

**Architecture:** A new `SettingsLayout` renders a role-filtered tab bar plus an `<Outlet />`; each tab is a nested child route rendering the existing, untouched page component. The active tab is derived from the URL. Non-admins reach only the Usage tab (per-tab route guards block deep links to admin tabs). The sidebar collapses six entries into one.

**Tech Stack:** React, react-router-dom v6, Radix Tabs (`@/shared/components/ui/tabs`), TanStack Query, Vitest + Testing Library.

## Global Constraints

- TDD is mandatory: failing test → confirm fail → minimal code → confirm pass.
- TypeScript (Google TS style); organized/sorted imports; American English naming.
- Test runner: `cd frontend && npx vitest run <file>` (single run, no watch).
- Type check: `cd frontend && npx tsc --noEmit`.
- Access rules are centralized in `frontend/src/features/auth/roles.ts` (`ROUTE_ROLES` + `canAccess`) — the single source of truth shared by the sidebar and the tab filter.
- Thai UI labels are copied verbatim; do not translate or invent new copy.

---

### Task 1: Open `/settings` to all roles and register child-route access

**Files:**
- Modify: `frontend/src/features/auth/roles.ts`
- Test: `frontend/src/features/auth/roles.test.ts` (create)

**Interfaces:**
- Consumes: existing `canAccess(role, path)` and `ROUTE_ROLES` in `roles.ts`.
- Produces: `ROUTE_ROLES` now contains `/settings` = all roles and entries for the six child paths (`/settings/system`, `/settings/llm`, `/settings/api-keys`, `/settings/usage`, `/settings/connections`, `/settings/audit`). `canAccess("user", "/settings/usage") === true`; `canAccess("user", "/settings/audit") === false`; `canAccess("user", "/settings") === true`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/auth/roles.test.ts`:

```typescript
import { describe, expect, it } from "vitest";

import { canAccess } from "./roles";

describe("settings route roles", () => {
  it("lets every role reach the settings area (holds the all-roles Usage tab)", () => {
    expect(canAccess("user", "/settings")).toBe(true);
    expect(canAccess("admin", "/settings")).toBe(true);
  });

  it("lets every role reach the Usage tab", () => {
    expect(canAccess("user", "/settings/usage")).toBe(true);
  });

  it("restricts the admin-only tabs to admins", () => {
    for (const path of [
      "/settings/system",
      "/settings/llm",
      "/settings/api-keys",
      "/settings/connections",
      "/settings/audit",
    ]) {
      expect(canAccess("user", path)).toBe(false);
      expect(canAccess("admin", path)).toBe(true);
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/features/auth/roles.test.ts`
Expected: FAIL — `canAccess("user", "/settings")` returns `false` (currently `/settings` is ADMIN), and child paths are unknown.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/features/auth/roles.ts`, change the `/settings` entry from `ADMIN` to `ALL` and add the six child entries. The `ROUTE_ROLES` object becomes:

```typescript
export const ROUTE_ROLES: Record<string, Role[]> = {
  "/chat": ALL,
  "/architecture": ALL,
  "/dashboard": ALL,
  "/executive": ALL,
  "/health": ALL,
  "/heatmap": ALL,
  "/usage": ALL,
  "/feedback": ALL,
  "/agencies": ADMIN,
  "/agencies/:id": ADMIN,
  "/history": ALL,
  "/connection-logs": ADMIN,
  "/api-keys": ADMIN,
  "/agencies/new": ADMIN,
  "/agencies/:id/setup": ADMIN,
  "/users": ADMIN,
  "/audit-log": ADMIN,
  "/settings": ALL,
  "/settings/system": ADMIN,
  "/settings/llm": ADMIN,
  "/settings/api-keys": ADMIN,
  "/settings/usage": ALL,
  "/settings/connections": ADMIN,
  "/settings/audit": ADMIN,
  "/llm-settings": ADMIN,
  "/popular-questions": ADMIN,
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/features/auth/roles.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/features/auth/roles.ts frontend/src/features/auth/roles.test.ts
rtk git commit -m "feat(settings): open /settings to all roles, register child-route access

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `SettingsLayout` — tab shell with role filtering and index redirect

**Files:**
- Create: `frontend/src/features/settings/SettingsLayout.tsx`
- Test: `frontend/src/features/settings/SettingsLayout.test.tsx` (create)

**Interfaces:**
- Consumes: `useAuth()` (returns `{ user: { role } | null, isAdmin }`), `canAccess` from `roles.ts` (Task 1), Radix `Tabs`/`TabsList`/`TabsTrigger`, react-router `Outlet`/`Navigate`/`useLocation`/`useNavigate`.
- Produces:
  - `default SettingsLayout` — renders the header, a role-filtered `TabsList`, and `<Outlet />`.
  - `SettingsIndexRedirect` (named export) — `<Navigate to={isAdmin ? "/settings/system" : "/settings/usage"} replace />`.
  - `SETTINGS_TABS` (named export) — `Array<{ label: string; path: string }>` in tab order.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/settings/SettingsLayout.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import SettingsLayout, { SettingsIndexRedirect } from "./SettingsLayout";

const mockUseAuth = vi.fn();
vi.mock("@/features/auth/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<SettingsIndexRedirect />} />
          <Route path="system" element={<div>SYSTEM PANEL</div>} />
          <Route path="usage" element={<div>USAGE PANEL</div>} />
          <Route path="audit" element={<div>AUDIT PANEL</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("SettingsLayout", () => {
  it("shows all six tabs for an admin", () => {
    mockUseAuth.mockReturnValue({ user: { role: "admin" }, isAdmin: true });
    renderAt("/settings/system");
    for (const label of [
      "ตั้งค่าระบบ",
      "LLM",
      "API Keys",
      "การใช้งาน API Key",
      "ประวัติการเชื่อมต่อ",
      "บันทึกการตรวจสอบ",
    ]) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
  });

  it("shows only the Usage tab for a non-admin", () => {
    mockUseAuth.mockReturnValue({ user: { role: "user" }, isAdmin: false });
    renderAt("/settings/usage");
    expect(screen.getByRole("tab", { name: "การใช้งาน API Key" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "API Keys" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "บันทึกการตรวจสอบ" })).not.toBeInTheDocument();
  });

  it("marks the tab matching the URL as active", () => {
    mockUseAuth.mockReturnValue({ user: { role: "admin" }, isAdmin: true });
    renderAt("/settings/audit");
    expect(screen.getByRole("tab", { name: "บันทึกการตรวจสอบ" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });

  it("redirects the index to the system tab for an admin", () => {
    mockUseAuth.mockReturnValue({ user: { role: "admin" }, isAdmin: true });
    renderAt("/settings");
    expect(screen.getByText("SYSTEM PANEL")).toBeInTheDocument();
  });

  it("redirects the index to the usage tab for a non-admin", () => {
    mockUseAuth.mockReturnValue({ user: { role: "user" }, isAdmin: false });
    renderAt("/settings");
    expect(screen.getByText("USAGE PANEL")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/features/settings/SettingsLayout.test.tsx`
Expected: FAIL — `SettingsLayout` module does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/features/settings/SettingsLayout.tsx`:

```tsx
import { Settings } from "lucide-react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/useAuth";
import { canAccess } from "@/features/auth/roles";
import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";

interface SettingsTab {
  label: string;
  path: string;
}

export const SETTINGS_TABS: SettingsTab[] = [
  { label: "ตั้งค่าระบบ", path: "/settings/system" },
  { label: "LLM", path: "/settings/llm" },
  { label: "API Keys", path: "/settings/api-keys" },
  { label: "การใช้งาน API Key", path: "/settings/usage" },
  { label: "ประวัติการเชื่อมต่อ", path: "/settings/connections" },
  { label: "บันทึกการตรวจสอบ", path: "/settings/audit" },
];

export function SettingsIndexRedirect() {
  const { isAdmin } = useAuth();
  return <Navigate to={isAdmin ? "/settings/system" : "/settings/usage"} replace />;
}

export default function SettingsLayout() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const tabs = user ? SETTINGS_TABS.filter((t) => canAccess(user.role, t.path)) : [];
  const active = tabs.find((t) => t.path === location.pathname)?.path ?? tabs[0]?.path;

  return (
    <div>
      <div className="p-4 md:p-6 pb-0">
        <div className="mb-4 flex items-center gap-2">
          <Settings className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-semibold">ตั้งค่าระบบ</h1>
        </div>
        <Tabs value={active} onValueChange={(v) => navigate(v)}>
          <TabsList className="flex h-auto flex-wrap">
            {tabs.map((t) => (
              <TabsTrigger key={t.path} value={t.path}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      <Outlet />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/features/settings/SettingsLayout.test.tsx`
Expected: PASS (all five tests)

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/features/settings/SettingsLayout.tsx frontend/src/features/settings/SettingsLayout.test.tsx
rtk git commit -m "feat(settings): add SettingsLayout tab shell with role filtering

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Wire nested Settings routes and redirect old URLs in `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `SettingsLayout` + `SettingsIndexRedirect` (Task 2); existing lazy page components (`SettingsPage`, `LlmSettingsPage`, `ApiKeysPage`, `UsageAnalyticsPage`, `ConnectionLogsPage`, `AuditLogPage`); `ProtectedRoute`; react-router `Navigate`.
- Produces: route tree where `/settings` renders `SettingsLayout` with nested tab routes, and the old top-level routes redirect in.

This task has no isolated unit test (route wiring is integration). Its gate is `tsc --noEmit` + the full frontend test suite passing + the Task 2 tests still green. Verify carefully.

- [ ] **Step 1: Add the SettingsLayout import**

At the top of `frontend/src/App.tsx`, `SettingsLayout` is lazy-loaded but `SettingsIndexRedirect` is a tiny named export used eagerly. Add near the other lazy declarations (after the existing `SettingsPage` line, line ~32):

```tsx
const SettingsLayout = lazy(() => import("@/features/settings/SettingsLayout"));
```

And add a static import for the redirect helper at the top with the other static imports (after the `AppLayout` import, line ~11):

```tsx
import { SettingsIndexRedirect } from "@/features/settings/SettingsLayout";
```

- [ ] **Step 2: Replace the admin route block for the merged pages**

In `frontend/src/App.tsx`, the current authenticated section has `/usage` under "Every authenticated role" and `/connection-logs`, `/api-keys`, `/audit-log` inside the `allowedRoles={["admin"]}` group, plus standalone `/settings` and `/llm-settings` routes.

Make these edits:

Remove the standalone Usage route line under "Every authenticated role":

```tsx
<Route path="/usage" element={<UsageAnalyticsPage />} />
```

Remove these three lines from the `allowedRoles={["admin"]}` group:

```tsx
<Route path="/connection-logs" element={<ConnectionLogsPage />} />
<Route path="/api-keys" element={<ApiKeysPage />} />
<Route path="/audit-log" element={<AuditLogPage />} />
```

Replace the two standalone lines:

```tsx
<Route path="/settings" element={<ProtectedRoute requireAdmin><SettingsPage /></ProtectedRoute>} />
<Route path="/llm-settings" element={<ProtectedRoute requireAdmin><LlmSettingsPage /></ProtectedRoute>} />
<Route path="/llm-providers" element={<Navigate to="/llm-settings" replace />} />
<Route path="/llm-routes" element={<Navigate to="/llm-settings" replace />} />
```

with the merged tree plus redirects:

```tsx
{/* Merged Settings area — nested tabs. /settings is authenticated-only
    because it contains the all-roles Usage tab; admin tabs are guarded
    individually so deep links are blocked, not just hidden. */}
<Route path="/settings" element={<SettingsLayout />}>
  <Route index element={<SettingsIndexRedirect />} />
  <Route path="system" element={<ProtectedRoute requireAdmin><SettingsPage /></ProtectedRoute>} />
  <Route path="llm" element={<ProtectedRoute requireAdmin><LlmSettingsPage /></ProtectedRoute>} />
  <Route path="api-keys" element={<ProtectedRoute requireAdmin><ApiKeysPage /></ProtectedRoute>} />
  <Route path="usage" element={<UsageAnalyticsPage />} />
  <Route path="connections" element={<ProtectedRoute requireAdmin><ConnectionLogsPage /></ProtectedRoute>} />
  <Route path="audit" element={<ProtectedRoute requireAdmin><AuditLogPage /></ProtectedRoute>} />
</Route>

{/* Redirect old top-level routes to their new tab */}
<Route path="/api-keys" element={<Navigate to="/settings/api-keys" replace />} />
<Route path="/usage" element={<Navigate to="/settings/usage" replace />} />
<Route path="/connection-logs" element={<Navigate to="/settings/connections" replace />} />
<Route path="/audit-log" element={<Navigate to="/settings/audit" replace />} />
<Route path="/llm-settings" element={<Navigate to="/settings/llm" replace />} />
<Route path="/llm-providers" element={<Navigate to="/settings/llm" replace />} />
<Route path="/llm-routes" element={<Navigate to="/settings/llm" replace />} />
```

Leave `/popular-questions` and all other routes unchanged.

- [ ] **Step 3: Type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. (If an imported page component is now only referenced inside the nested tree, that's fine — all six are still referenced.)

- [ ] **Step 4: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS — including the Task 1 and Task 2 tests and all existing per-component tests.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/App.tsx
rtk git commit -m "feat(settings): nest admin pages under /settings tabs, redirect old URLs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Collapse the six sidebar entries into one Settings entry

**Files:**
- Modify: `frontend/src/shared/components/layout/AppSidebar.tsx`

**Interfaces:**
- Consumes: existing `navItems` array and `canAccess`-based filtering already in `AppSidebar.tsx`; `/settings` now resolves to all roles (Task 1).
- Produces: a single `{ title: "ตั้งค่าระบบ", url: "/settings", icon: Settings }` nav entry replacing the six merged ones.

This is a small presentational change; its gate is `tsc --noEmit` and visual/manual confirmation. There is no dedicated sidebar unit test in the repo; do not add one.

- [ ] **Step 1: Edit `navItems`**

In `frontend/src/shared/components/layout/AppSidebar.tsx`, the `navItems` array (currently reordered in the working tree) contains these six entries to remove:

```tsx
{ title: "ตั้งค่าระบบ", url: "/settings", icon: Settings },
{ title: "LLM Settings", url: "/llm-settings", icon: Cpu },
{ title: "API Keys", url: "/api-keys", icon: KeyRound },
{ title: "การใช้งาน API Key", url: "/usage", icon: BarChart3 },
{ title: "ประวัติการเชื่อมต่อ", url: "/connection-logs", icon: Activity },
{ title: "บันทึกการตรวจสอบ", url: "/audit-log", icon: ScrollText },
```

Replace all six with a single entry (keep it where the settings group sat, before `จัดการผู้ใช้`/Architecture):

```tsx
{ title: "ตั้งค่าระบบ", url: "/settings", icon: Settings },
```

The final `navItems` should be:

```tsx
const navItems = [
  { title: "แชทใหม่", url: "/chat", icon: MessageSquare },
  { title: "Dashboard", url: "/dashboard", icon: LayoutDashboard },
  { title: "Executive", url: "/executive", icon: Briefcase },
  { title: "Agency Health", url: "/health", icon: Activity },
  { title: "Usage Heatmap", url: "/heatmap", icon: Flame },
  { title: "จัดการหน่วยงาน", url: "/agencies", icon: Building2 },
  { title: "ประวัติการสนทนา", url: "/history", icon: History },
  { title: "ความคิดเห็นและความพึงพอใจ", url: "/feedback", icon: MessageSquareWarning },
  { title: "คำถามยอดนิยม", url: "/popular-questions", icon: Sparkles },
  { title: "ตั้งค่าระบบ", url: "/settings", icon: Settings },
  { title: "จัดการผู้ใช้", url: "/users", icon: Users },
  { title: "Architecture", url: "/architecture", icon: Network },
];
```

- [ ] **Step 2: Remove now-unused icon imports**

The icons `KeyRound`, `BarChart3`, `ScrollText`, and `Cpu` are no longer used (verify none remain referenced elsewhere in the file). Remove them from the top `lucide-react` import so `tsc` stays clean. `Activity` stays (used by "Agency Health"). The import line becomes:

```tsx
import { MessageSquare, LayoutDashboard, Building2, History, Network, LogOut, Activity, Briefcase, Flame, Settings, Users, MessageSquareWarning, Sparkles } from "lucide-react";
```

- [ ] **Step 3: Type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors, no "declared but never used" warnings for the removed icons.

- [ ] **Step 4: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/shared/components/layout/AppSidebar.tsx
rtk git commit -m "feat(settings): collapse six sidebar entries into one Settings link

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Manual verification + update CONTEXT.md

**Files:**
- Modify: `CONTEXT.md` (project convention: update after any change)

**Interfaces:**
- Consumes: the completed feature.
- Produces: updated project context notes.

- [ ] **Step 1: Manual smoke test (dev server)**

Run: `cd frontend && npx vite` (or the project's usual dev command). As an admin, confirm:
- The sidebar shows one "ตั้งค่าระบบ" entry.
- `/settings` lands on the System tab; all six tabs are visible and switch the URL (`/settings/llm`, `/settings/api-keys`, `/settings/usage`, `/settings/connections`, `/settings/audit`).
- Visiting old URLs (`/api-keys`, `/usage`, `/connection-logs`, `/audit-log`, `/llm-settings`, `/llm-providers`, `/llm-routes`) redirects to the matching tab.

As a non-admin (role `user`), confirm:
- The sidebar still shows the "ตั้งค่าระบบ" entry.
- `/settings` lands on the Usage tab and only the Usage tab is shown.
- Deep-linking to `/settings/audit` is blocked by the `requireAdmin` guard.

- [ ] **Step 2: Update `CONTEXT.md`**

Add a short note under the frontend/navigation section recording that the six admin pages are now tabs under `/settings` (`SettingsLayout`), routes are nested with redirects from the old URLs, and `/settings` is all-roles with per-tab admin guards. Match the file's existing tone and length.

- [ ] **Step 3: Commit**

```bash
rtk git add CONTEXT.md
rtk git commit -m "docs: note tabbed Settings area in CONTEXT.md

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- `SettingsLayout` tab shell + role filter → Task 2. ✓
- Nested routing + index role redirect + old-URL redirects → Task 3 (routes) + Task 2 (`SettingsIndexRedirect`). ✓
- Sidebar collapse to one entry → Task 4. ✓
- `roles.ts` `/settings` → ALL + child entries → Task 1. ✓
- Existing page components untouched → confirmed; no task modifies them. ✓
- Per-tab guard so non-admin deep links blocked → Task 3 (`requireAdmin` per admin child). ✓
- Tests (all-tabs admin, usage-only non-admin, index redirect, active tab) → Task 2. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `SETTINGS_TABS`, `SettingsIndexRedirect`, and `SettingsLayout` names/signatures match between Task 2 (definition), Task 3 (consumption), and the tests. Child route paths (`system`, `llm`, `api-keys`, `usage`, `connections`, `audit`) and their absolute forms in `ROUTE_ROLES` (Task 1) and `SETTINGS_TABS` (Task 2) agree. ✓
