import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BindingsPanel } from "./BindingsPanel";
import type { LlmBinding } from "./llmBindingApi";
import type { LlmProvider } from "@/features/llm-providers/llmProviderApi";

const mockListBindings = vi.fn();
const mockUpdateBinding = vi.fn();

vi.mock("@/features/llm-bindings/llmBindingApi", () => ({
  listBindings: (...args: unknown[]) => mockListBindings(...args),
  updateBinding: (...args: unknown[]) => mockUpdateBinding(...args),
  testBinding: vi.fn(),
}));

const mockListProviders = vi.fn();
vi.mock("@/features/llm-providers/llmProviderApi", () => ({
  listProviders: (...args: unknown[]) => mockListProviders(...args),
}));

const makeBinding = (overrides: Partial<LlmBinding> = {}): LlmBinding => ({
  id: "b1",
  purpose: "chat",
  provider_id: "p1",
  provider_name: "OpenAI",
  model: "gpt-4o",
  model_override: null,
  timeout_override: null,
  enabled: true,
  ...overrides,
});

const makeProvider = (overrides: Partial<LlmProvider> = {}): LlmProvider => ({
  id: "p1",
  name: "OpenAI",
  provider: "openai",
  model: "gpt-4o",
  base_url: "https://api.openai.com/v1",
  api_key: "*****",
  headers: [],
  timeout_seconds: 60,
  max_retries: 2,
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
      <BindingsPanel />
    </QueryClientProvider>,
  );
}

describe("BindingsPanel edit-only", () => {
  beforeEach(() => {
    mockListProviders.mockResolvedValue({
      data: [makeProvider({ id: "p1", name: "OpenAI" }), makeProvider({ id: "p2", name: "Azure" })],
      total: 2,
    });
  });
  afterEach(() => vi.clearAllMocks());

  it("does not show a create button", async () => {
    mockListBindings.mockResolvedValue({ data: [makeBinding()], total: 1 });
    renderPanel();
    await screen.findByText("chat");
    expect(screen.queryByText("เพิ่มการผูก")).not.toBeInTheDocument();
  });

  it("renders binding cards but no delete control", async () => {
    mockListBindings.mockResolvedValue({ data: [makeBinding({ purpose: "chat" })], total: 1 });
    renderPanel();
    await screen.findByText("chat");
    expect(screen.getByRole("button", { name: "แก้ไข" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ลบ" })).not.toBeInTheDocument();
  });

  it("opens the edit dialog and sends model_override/provider, omitting purpose", async () => {
    const binding = makeBinding({ id: "b1", purpose: "chat", provider_id: "p1" });
    mockListBindings.mockResolvedValue({ data: [binding], total: 1 });
    mockUpdateBinding.mockResolvedValue({ ...binding, model_override: "gpt-4o-mini" });
    renderPanel();

    await screen.findByText("chat");
    await userEvent.click(screen.getByRole("button", { name: "แก้ไข" }));

    const modelInput = screen.getByLabelText("โมเดลแทนที่ (Model override)");
    await userEvent.clear(modelInput);
    await userEvent.type(modelInput, "gpt-4o-mini");
    await userEvent.click(screen.getByLabelText("ผู้ให้บริการ (Provider)"));
    await userEvent.click(await screen.findByRole("option", { name: "Azure" }));
    await userEvent.click(screen.getByRole("button", { name: /บันทึก/ }));

    await waitFor(() => expect(mockUpdateBinding).toHaveBeenCalled());
    const [id, body] = mockUpdateBinding.mock.calls[0];
    expect(id).toBe("b1");
    expect(body).not.toHaveProperty("purpose");
    expect(body.model_override).toBe("gpt-4o-mini");
    expect(body.provider_id).toBe("p2");
  });
});
