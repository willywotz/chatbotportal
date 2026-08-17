# Merge LLM Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the `/llm-providers` and `/llm-routes` admin pages into one `/llm-settings` page (Providers left, Routes right) where Routes are edit-only.

**Architecture:** Extract each old page body into a self-contained panel component (`ProvidersPanel`, `RoutesPanel`) that owns its own React Query + mutation state. A new `LlmSettingsPage` composes the two in a responsive grid. Routes lose Create and Delete; Providers keep full CRUD. Old routes redirect to the new one.

**Tech Stack:** React 18, TypeScript, React Router v6, TanStack Query v5, Vitest + Testing Library, Tailwind, shadcn/ui, sonner (toasts).

## Global Constraints

- **Working dir for all commands:** `frontend/` (the React app). Paths below are relative to `frontend/`.
- **Test runner:** `rtk vitest run <path>` (npm script `test` = `vitest run`). Run from `frontend/`.
- **TDD mandatory:** failing test → confirm fail → minimal code → confirm pass → commit.
- **Google TS/HTML-CSS style**; American English identifiers; organized (path-sorted) imports.
- **UI copy stays Thai**, matching existing strings verbatim (e.g. `เส้นทาง LLM`, `ผู้ให้บริการ LLM`).
- **No backend/API changes.** `createRoute` / `deleteRoute` in `llmRouteApi.ts` stay exported (harmless if unused).
- **Commit with git via `rtk`**, e.g. `rtk git add … && rtk git commit -m "…"`.

---

### Task 1: Extract ProvidersPanel

Verbatim extraction of the current `LlmProvidersPage` body into a reusable panel (full create/edit/delete kept). Only difference: the panel returns `space-y-4` content with no outer page padding — the future page owns padding.

**Files:**
- Create: `src/features/llm-providers/ProvidersPanel.tsx`
- Test: `src/features/llm-providers/ProvidersPanel.test.tsx`

**Interfaces:**
- Consumes: `listProviders`, `createProvider`, `updateProvider`, `deleteProvider`, `LlmProvider`, `LlmProviderInput` from `./llmProviderApi`; `LlmProviderList`, `CreateLlmProviderDialog`, `EditLlmProviderDialog`, `DeleteLlmProviderDialog`.
- Produces: `export function ProvidersPanel(): JSX.Element` (named export, no props).

- [ ] **Step 1: Write the failing test**

Create `src/features/llm-providers/ProvidersPanel.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProvidersPanel } from "./ProvidersPanel";
import type { LlmProvider } from "./llmProviderApi";

const mockListProviders = vi.fn();
const mockCreateProvider = vi.fn();
const mockUpdateProvider = vi.fn();
const mockDeleteProvider = vi.fn();

vi.mock("@/features/llm-providers/llmProviderApi", () => ({
  listProviders: (...args: unknown[]) => mockListProviders(...args),
  createProvider: (...args: unknown[]) => mockCreateProvider(...args),
  updateProvider: (...args: unknown[]) => mockUpdateProvider(...args),
  deleteProvider: (...args: unknown[]) => mockDeleteProvider(...args),
}));

const makeProvider = (overrides: Partial<LlmProvider> = {}): LlmProvider => ({
  id: "p1",
  name: "OpenAI",
  base_url: "https://api.openai.com/v1",
  api_key: "*****",
  auth_header: "Authorization",
  auth_scheme: "Bearer",
  timeout_seconds: 60,
  request_usage: false,
  rate_limit_rps: null,
  rate_limit_rpm: null,
  max_queue_size: 50,
  enabled: true,
  ...overrides,
});

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProvidersPanel />
    </QueryClientProvider>,
  );
}

describe("ProvidersPanel create button", () => {
  beforeEach(() => mockListProviders.mockResolvedValue({ data: [], total: 0 }));
  afterEach(() => vi.clearAllMocks());

  it("shows the create button", async () => {
    renderPanel();
    expect(await screen.findByText("เพิ่มผู้ให้บริการ")).toBeInTheDocument();
  });
});

describe("ProvidersPanel list rendering", () => {
  afterEach(() => vi.clearAllMocks());

  it("shows empty state when there are no providers", async () => {
    mockListProviders.mockResolvedValue({ data: [], total: 0 });
    renderPanel();
    expect(await screen.findByText("ยังไม่มีผู้ให้บริการ LLM กรุณาเพิ่มใหม่")).toBeInTheDocument();
  });

  it("renders provider cards with name", async () => {
    mockListProviders.mockResolvedValue({
      data: [makeProvider({ id: "p1", name: "OpenAI" }), makeProvider({ id: "p2", name: "Azure", enabled: false })],
      total: 2,
    });
    renderPanel();
    expect(await screen.findByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Azure")).toBeInTheDocument();
    expect(screen.getByText("ปิดใช้งาน")).toBeInTheDocument();
  });
});

describe("ProvidersPanel edit flow", () => {
  afterEach(() => vi.clearAllMocks());

  it("omits api_key from the update payload when left blank", async () => {
    const provider = makeProvider({ id: "p1", name: "Old Name" });
    mockListProviders.mockResolvedValue({ data: [provider], total: 1 });
    mockUpdateProvider.mockResolvedValue({ ...provider, name: "New Name" });
    renderPanel();

    await screen.findByText("Old Name");
    await userEvent.click(screen.getByRole("button", { name: "แก้ไข" }));
    const nameInput = screen.getByLabelText("ชื่อ");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "New Name");
    await userEvent.click(screen.getByRole("button", { name: /บันทึก/ }));

    await waitFor(() => expect(mockUpdateProvider).toHaveBeenCalled());
    const [id, body] = mockUpdateProvider.mock.calls[0];
    expect(id).toBe("p1");
    expect(body).not.toHaveProperty("api_key");
    expect(body.name).toBe("New Name");
  });
});

describe("ProvidersPanel delete flow", () => {
  afterEach(() => vi.clearAllMocks());

  it("calls deleteProvider with the correct id on confirm", async () => {
    mockListProviders.mockResolvedValue({ data: [makeProvider({ id: "p1", name: "Provider To Delete" })], total: 1 });
    mockDeleteProvider.mockResolvedValue(undefined);
    renderPanel();

    await screen.findByText("Provider To Delete");
    await userEvent.click(screen.getByRole("button", { name: "ลบ" }));
    await screen.findByText("ยืนยันการลบ");
    const confirmBtn = screen
      .getAllByRole("button")
      .find((b) => b.textContent?.trim() === "ลบ" && !b.hasAttribute("aria-label"));
    await userEvent.click(confirmBtn!);

    await waitFor(() => expect(mockDeleteProvider).toHaveBeenCalledWith("p1"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk vitest run src/features/llm-providers/ProvidersPanel.test.tsx`
Expected: FAIL — cannot resolve `./ProvidersPanel` / `ProvidersPanel is not exported`.

- [ ] **Step 3: Write minimal implementation**

Create `src/features/llm-providers/ProvidersPanel.tsx`:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { CreateLlmProviderDialog } from "./CreateLlmProviderDialog";
import { DeleteLlmProviderDialog } from "./DeleteLlmProviderDialog";
import { EditLlmProviderDialog } from "./EditLlmProviderDialog";
import { LlmProviderList } from "./LlmProviderList";
import {
  createProvider,
  deleteProvider,
  listProviders,
  updateProvider,
  type LlmProvider,
  type LlmProviderInput,
} from "./llmProviderApi";
import { Button } from "@/shared/components/ui/button";

const QUERY_KEY = ["llm-providers"];

export function ProvidersPanel() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: QUERY_KEY, queryFn: listProviders });
  const providers = data?.data ?? [];

  const [createOpen, setCreateOpen] = useState(false);
  const createMutation = useMutation({
    mutationFn: (input: LlmProviderInput) => createProvider(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      toast.success("สร้างผู้ให้บริการ LLM เรียบร้อย");
      setCreateOpen(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const [editTarget, setEditTarget] = useState<LlmProvider | null>(null);
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<LlmProviderInput> }) => updateProvider(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      toast.success("แก้ไขผู้ให้บริการ LLM เรียบร้อย");
      setEditTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const [deleteTarget, setDeleteTarget] = useState<LlmProvider | null>(null);
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProvider(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      toast.success("ลบผู้ให้บริการ LLM เรียบร้อย");
      setDeleteTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">ผู้ให้บริการ LLM</h2>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          เพิ่มผู้ให้บริการ
        </Button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && (
        <LlmProviderList providers={providers} onEdit={setEditTarget} onDelete={setDeleteTarget} />
      )}

      <CreateLlmProviderDialog open={createOpen} mutation={createMutation} onClose={() => setCreateOpen(false)} />
      <EditLlmProviderDialog target={editTarget} mutation={editMutation} onClose={() => setEditTarget(null)} />
      <DeleteLlmProviderDialog
        target={deleteTarget}
        mutation={deleteMutation}
        onConfirm={() => deleteMutation.mutate(deleteTarget!.id)}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk vitest run src/features/llm-providers/ProvidersPanel.test.tsx`
Expected: PASS (all describes green).

- [ ] **Step 5: Commit**

```bash
rtk git add src/features/llm-providers/ProvidersPanel.tsx src/features/llm-providers/ProvidersPanel.test.tsx
rtk git commit -m "feat(llm): extract ProvidersPanel from LlmProvidersPage"
```

---

### Task 2: Extract edit-only RoutesPanel

Create `RoutesPanel` (edit-only: no create, no delete). Make `LlmRoutesList`'s `onDelete` optional and render the Delete button only when it is supplied — this keeps the still-present `LlmRoutesPage` compiling until Task 4 removes it, while `RoutesPanel` renders no Delete button.

**Files:**
- Modify: `src/features/llm-routes/LlmRoutesList.tsx`
- Create: `src/features/llm-routes/RoutesPanel.tsx`
- Test: `src/features/llm-routes/RoutesPanel.test.tsx`

**Interfaces:**
- Consumes: `listRoutes`, `updateRoute`, `LlmRoute`, `LlmRouteInput` from `./llmRouteApi`; `listProviders` from `@/features/llm-providers/llmProviderApi`; `LlmRoutesList`, `EditLlmRouteDialog`.
- Produces: `export function RoutesPanel(): JSX.Element` (named export, no props); `LlmRoutesList` prop `onDelete?: (route: LlmRoute) => void` (now optional).

- [ ] **Step 1: Write the failing test**

Create `src/features/llm-routes/RoutesPanel.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RoutesPanel } from "./RoutesPanel";
import type { LlmRoute } from "./llmRouteApi";
import type { LlmProvider } from "@/features/llm-providers/llmProviderApi";

const mockListRoutes = vi.fn();
const mockUpdateRoute = vi.fn();

vi.mock("@/features/llm-routes/llmRouteApi", () => ({
  listRoutes: (...args: unknown[]) => mockListRoutes(...args),
  updateRoute: (...args: unknown[]) => mockUpdateRoute(...args),
}));

const mockListProviders = vi.fn();
vi.mock("@/features/llm-providers/llmProviderApi", () => ({
  listProviders: (...args: unknown[]) => mockListProviders(...args),
}));

const makeRoute = (overrides: Partial<LlmRoute> = {}): LlmRoute => ({
  id: "r1",
  purpose: "chat",
  provider_id: "p1",
  provider_name: "OpenAI",
  model: "gpt-4o",
  timeout_override: null,
  enabled: true,
  ...overrides,
});

const makeProvider = (overrides: Partial<LlmProvider> = {}): LlmProvider => ({
  id: "p1",
  name: "OpenAI",
  base_url: "https://api.openai.com/v1",
  api_key: "*****",
  auth_header: "Authorization",
  auth_scheme: "Bearer",
  timeout_seconds: 60,
  request_usage: false,
  rate_limit_rps: null,
  rate_limit_rpm: null,
  max_queue_size: 50,
  enabled: true,
  ...overrides,
});

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RoutesPanel />
    </QueryClientProvider>,
  );
}

describe("RoutesPanel edit-only", () => {
  beforeEach(() => {
    mockListProviders.mockResolvedValue({
      data: [makeProvider({ id: "p1", name: "OpenAI" }), makeProvider({ id: "p2", name: "Azure" })],
      total: 2,
    });
  });
  afterEach(() => vi.clearAllMocks());

  it("does not show a create button", async () => {
    mockListRoutes.mockResolvedValue({ data: [makeRoute()], total: 1 });
    renderPanel();
    await screen.findByText("chat");
    expect(screen.queryByText("เพิ่มเส้นทาง")).not.toBeInTheDocument();
  });

  it("renders route cards but no delete control", async () => {
    mockListRoutes.mockResolvedValue({ data: [makeRoute({ purpose: "chat" })], total: 1 });
    renderPanel();
    await screen.findByText("chat");
    expect(screen.getByRole("button", { name: "แก้ไข" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ลบ" })).not.toBeInTheDocument();
  });

  it("opens the edit dialog and sends the new model/provider, omitting purpose", async () => {
    const route = makeRoute({ id: "r1", purpose: "chat", provider_id: "p1", model: "gpt-4o" });
    mockListRoutes.mockResolvedValue({ data: [route], total: 1 });
    mockUpdateRoute.mockResolvedValue({ ...route, model: "gpt-4o-mini" });
    renderPanel();

    await screen.findByText("chat");
    await userEvent.click(screen.getByRole("button", { name: "แก้ไข" }));

    const modelInput = screen.getByLabelText("โมเดล (Model)");
    await userEvent.clear(modelInput);
    await userEvent.type(modelInput, "gpt-4o-mini");
    await userEvent.click(screen.getByLabelText("ผู้ให้บริการ (Provider)"));
    await userEvent.click(await screen.findByRole("option", { name: "Azure" }));
    await userEvent.click(screen.getByRole("button", { name: /บันทึก/ }));

    await waitFor(() => expect(mockUpdateRoute).toHaveBeenCalled());
    const [id, body] = mockUpdateRoute.mock.calls[0];
    expect(id).toBe("r1");
    expect(body).not.toHaveProperty("purpose");
    expect(body.model).toBe("gpt-4o-mini");
    expect(body.provider_id).toBe("p2");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk vitest run src/features/llm-routes/RoutesPanel.test.tsx`
Expected: FAIL — cannot resolve `./RoutesPanel`.

- [ ] **Step 3a: Make the Delete button optional in `LlmRoutesList`**

Edit `src/features/llm-routes/LlmRoutesList.tsx` — make `onDelete` optional and render the delete button only when provided:

```tsx
interface Props {
  routes: LlmRoute[];
  onEdit: (route: LlmRoute) => void;
  onDelete?: (route: LlmRoute) => void;
}

export function LlmRoutesList({ routes, onEdit, onDelete }: Props) {
```

Then in the row action group, wrap the delete `<button>` so it renders only when `onDelete` exists:

```tsx
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => onEdit(r)}
                  className="p-1.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="แก้ไข"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                {onDelete && (
                  <button
                    onClick={() => onDelete(r)}
                    className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                    aria-label="ลบ"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
```

(Keep the `Trash2` import — it is still referenced inside the conditional.)

- [ ] **Step 3b: Create `RoutesPanel`**

Create `src/features/llm-routes/RoutesPanel.tsx`:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { EditLlmRouteDialog } from "./EditLlmRouteDialog";
import { LlmRoutesList } from "./LlmRoutesList";
import { listRoutes, updateRoute, type LlmRoute, type LlmRouteInput } from "./llmRouteApi";
import { listProviders } from "@/features/llm-providers/llmProviderApi";

const QUERY_KEY = ["llm-routes"];

export function RoutesPanel() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: QUERY_KEY, queryFn: listRoutes });
  const routes = data?.data ?? [];

  const { data: providersData, isLoading: providersLoading } = useQuery({
    queryKey: ["llm-providers"],
    queryFn: listProviders,
  });
  const providers = providersData?.data ?? [];

  const [editTarget, setEditTarget] = useState<LlmRoute | null>(null);
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<LlmRouteInput> }) => updateRoute(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      toast.success("แก้ไขเส้นทาง LLM เรียบร้อย");
      setEditTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">เส้นทาง LLM</h2>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && <LlmRoutesList routes={routes} onEdit={setEditTarget} />}

      <EditLlmRouteDialog
        target={editTarget}
        providers={providers}
        providersLoading={providersLoading}
        mutation={editMutation}
        onClose={() => setEditTarget(null)}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk vitest run src/features/llm-routes/RoutesPanel.test.tsx src/features/llm-routes/LlmRoutesPage.test.tsx`
Expected: PASS. (The old `LlmRoutesPage.test.tsx` still passes because `onDelete` is still supplied there and the Delete button still renders.)

- [ ] **Step 5: Commit**

```bash
rtk git add src/features/llm-routes/RoutesPanel.tsx src/features/llm-routes/RoutesPanel.test.tsx src/features/llm-routes/LlmRoutesList.tsx
rtk git commit -m "feat(llm): add edit-only RoutesPanel; make list delete optional"
```

---

### Task 3: Compose LlmSettingsPage

New default-export page that renders both panels in a responsive grid: stacked on mobile, Providers-left/Routes-right on `md`+.

**Files:**
- Create: `src/features/llm/LlmSettingsPage.tsx`
- Test: `src/features/llm/LlmSettingsPage.test.tsx`

**Interfaces:**
- Consumes: `ProvidersPanel` from `@/features/llm-providers/ProvidersPanel`; `RoutesPanel` from `@/features/llm-routes/RoutesPanel`.
- Produces: `export default function LlmSettingsPage(): JSX.Element`.

- [ ] **Step 1: Write the failing test**

Create `src/features/llm/LlmSettingsPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LlmSettingsPage from "./LlmSettingsPage";
import type { LlmProvider } from "@/features/llm-providers/llmProviderApi";
import type { LlmRoute } from "@/features/llm-routes/llmRouteApi";

const mockListProviders = vi.fn();
vi.mock("@/features/llm-providers/llmProviderApi", () => ({
  listProviders: (...args: unknown[]) => mockListProviders(...args),
  createProvider: vi.fn(),
  updateProvider: vi.fn(),
  deleteProvider: vi.fn(),
}));

const mockListRoutes = vi.fn();
vi.mock("@/features/llm-routes/llmRouteApi", () => ({
  listRoutes: (...args: unknown[]) => mockListRoutes(...args),
  updateRoute: vi.fn(),
}));

const makeProvider = (o: Partial<LlmProvider> = {}): LlmProvider => ({
  id: "p1",
  name: "OpenAI",
  base_url: "https://api.openai.com/v1",
  api_key: "*****",
  auth_header: "Authorization",
  auth_scheme: "Bearer",
  timeout_seconds: 60,
  request_usage: false,
  rate_limit_rps: null,
  rate_limit_rpm: null,
  max_queue_size: 50,
  enabled: true,
  ...o,
});

const makeRoute = (o: Partial<LlmRoute> = {}): LlmRoute => ({
  id: "r1",
  purpose: "chat",
  provider_id: "p1",
  provider_name: "OpenAI",
  model: "gpt-4o",
  timeout_override: null,
  enabled: true,
  ...o,
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LlmSettingsPage />
    </QueryClientProvider>,
  );
}

describe("LlmSettingsPage", () => {
  beforeEach(() => {
    mockListProviders.mockResolvedValue({ data: [makeProvider()], total: 1 });
    mockListRoutes.mockResolvedValue({ data: [makeRoute()], total: 1 });
  });
  afterEach(() => vi.clearAllMocks());

  it("renders both the Providers and Routes panel headings", async () => {
    renderPage();
    expect(await screen.findByText("ผู้ให้บริการ LLM")).toBeInTheDocument();
    expect(await screen.findByText("เส้นทาง LLM")).toBeInTheDocument();
  });

  it("shows the provider Add button but no route Add button", async () => {
    renderPage();
    expect(await screen.findByText("เพิ่มผู้ให้บริการ")).toBeInTheDocument();
    expect(screen.queryByText("เพิ่มเส้นทาง")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk vitest run src/features/llm/LlmSettingsPage.test.tsx`
Expected: FAIL — cannot resolve `./LlmSettingsPage`.

- [ ] **Step 3: Write minimal implementation**

Create `src/features/llm/LlmSettingsPage.tsx`:

```tsx
import { ProvidersPanel } from "@/features/llm-providers/ProvidersPanel";
import { RoutesPanel } from "@/features/llm-routes/RoutesPanel";

export default function LlmSettingsPage() {
  return (
    <div className="p-4 md:p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
      <ProvidersPanel />
      <RoutesPanel />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk vitest run src/features/llm/LlmSettingsPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add src/features/llm/LlmSettingsPage.tsx src/features/llm/LlmSettingsPage.test.tsx
rtk git commit -m "feat(llm): add LlmSettingsPage composing both panels"
```

---

### Task 4: Wire routing, sidebar, and remove old pages

Point navigation at `/llm-settings`, redirect the old paths, delete the superseded pages/tests, and tighten `LlmRoutesList` (remove the now-unused optional `onDelete`).

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/shared/components/layout/AppSidebar.tsx`
- Modify: `src/features/llm-routes/LlmRoutesList.tsx`
- Delete: `src/features/llm-providers/LlmProvidersPage.tsx`, `src/features/llm-providers/LlmProvidersPage.test.tsx`, `src/features/llm-routes/LlmRoutesPage.tsx`, `src/features/llm-routes/LlmRoutesPage.test.tsx`

**Interfaces:**
- Consumes: `LlmSettingsPage` (default export) from `@/features/llm/LlmSettingsPage`.
- Produces: route `/llm-settings`; redirects `/llm-providers` and `/llm-routes` → `/llm-settings`; sidebar entry `{ title: "LLM Settings", url: "/llm-settings", icon: Cpu }`.

- [ ] **Step 1: Update `App.tsx` imports and routes**

In `src/App.tsx`, add `Navigate` to the react-router-dom import:

```tsx
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
```

Replace the two lazy imports (`LlmProvidersPage`, `LlmRoutesPage`) with one:

```tsx
const LlmSettingsPage = lazy(() => import("@/features/llm/LlmSettingsPage"));
```

Replace the two admin route lines:

```tsx
                <Route path="/llm-providers" element={<ProtectedRoute requireAdmin><LlmProvidersPage /></ProtectedRoute>} />
                <Route path="/llm-routes" element={<ProtectedRoute requireAdmin><LlmRoutesPage /></ProtectedRoute>} />
```

with:

```tsx
                <Route path="/llm-settings" element={<ProtectedRoute requireAdmin><LlmSettingsPage /></ProtectedRoute>} />
                <Route path="/llm-providers" element={<Navigate to="/llm-settings" replace />} />
                <Route path="/llm-routes" element={<Navigate to="/llm-settings" replace />} />
```

- [ ] **Step 2: Update the sidebar**

In `src/shared/components/layout/AppSidebar.tsx`, replace the two nav entries:

```tsx
  { title: "LLM Providers", url: "/llm-providers", icon: Cpu },
  { title: "LLM Routes", url: "/llm-routes", icon: Route },
```

with a single entry:

```tsx
  { title: "LLM Settings", url: "/llm-settings", icon: Cpu },
```

Then remove the now-unused `Route` icon from the `lucide-react` import in that file (leave `Cpu`, which is still used). Grep to confirm `Route` is not referenced elsewhere in the file before removing:

Run: `rtk grep "Route" src/shared/components/layout/AppSidebar.tsx`
Expected: no remaining usages of the `Route` icon (only the import line, which you delete).

- [ ] **Step 3: Delete the superseded pages and their tests**

```bash
rtk git rm src/features/llm-providers/LlmProvidersPage.tsx src/features/llm-providers/LlmProvidersPage.test.tsx src/features/llm-routes/LlmRoutesPage.tsx src/features/llm-routes/LlmRoutesPage.test.tsx
```

- [ ] **Step 4: Tighten `LlmRoutesList` (remove now-dead delete path)**

No consumer passes `onDelete` anymore. In `src/features/llm-routes/LlmRoutesList.tsx` remove the `onDelete` prop, the conditional delete button, and the `Trash2` import so the final file matches the edit-only design:

```tsx
import { Pencil } from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import type { LlmRoute } from "./llmRouteApi";

interface Props {
  routes: LlmRoute[];
  onEdit: (route: LlmRoute) => void;
}

export function LlmRoutesList({ routes, onEdit }: Props) {
```

and the row action group becomes just the edit button:

```tsx
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => onEdit(r)}
                  className="p-1.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="แก้ไข"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              </div>
```

- [ ] **Step 5: Verify the full suite, types, and build**

Run: `rtk vitest run`
Expected: PASS — no references to deleted pages; RoutesPanel/ProvidersPanel/LlmSettingsPage tests green.

Run: `rtk npm run lint`
Expected: no errors (no unused `Route` import, no unused symbols).

Run: `rtk npm run build`
Expected: `vite build` succeeds (TypeScript compiles; no dangling imports of deleted pages).

- [ ] **Step 6: Commit**

```bash
rtk git add -A
rtk git commit -m "feat(llm): route /llm-settings, redirect old paths, remove old pages"
```

---

## Post-implementation (orchestrator)

- Update `CONTEXT.md` to reflect the merged LLM Settings page and edit-only routes, then commit (per project CLAUDE.md).
- Optionally verify in the running app that `/llm-providers` and `/llm-routes` redirect to `/llm-settings` and the two-column layout renders.
