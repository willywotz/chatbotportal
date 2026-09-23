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
