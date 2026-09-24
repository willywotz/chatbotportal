import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LlmSettingsPage from "./LlmSettingsPage";
import type { LlmProvider } from "@/features/llm-providers/llmProviderApi";
import type { LlmBinding } from "@/features/llm-bindings/llmBindingApi";

const mockListProviders = vi.fn();
vi.mock("@/features/llm-providers/llmProviderApi", () => ({
  listProviders: (...args: unknown[]) => mockListProviders(...args),
  createProvider: vi.fn(),
  updateProvider: vi.fn(),
  deleteProvider: vi.fn(),
  listKinds: () => Promise.resolve({ data: ["openai"] }),
}));

const mockListBindings = vi.fn();
vi.mock("@/features/llm-bindings/llmBindingApi", () => ({
  listBindings: (...args: unknown[]) => mockListBindings(...args),
  updateBinding: vi.fn(),
  testBinding: vi.fn(),
}));

const makeProvider = (o: Partial<LlmProvider> = {}): LlmProvider => ({
  id: "p1",
  name: "OpenAI",
  provider: "openai",
  model: "gpt-4o",
  base_url: "https://api.openai.com/v1",
  api_key: "*****",
  timeout_seconds: 60,
  max_retries: 2,
  rate_limit_rps: null,
  rate_limit_rpm: null,
  max_queue_size: 50,
  enabled: true,
  ...o,
});

const makeBinding = (o: Partial<LlmBinding> = {}): LlmBinding => ({
  id: "b1",
  purpose: "classification",
  provider_id: "p1",
  provider_name: "OpenAI",
  model: "gpt-4o",
  model_override: null,
  fallback_binding_id: null,
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
    mockListBindings.mockResolvedValue({ data: [makeBinding()], total: 1 });
  });
  afterEach(() => vi.clearAllMocks());

  it("renders both the Providers and Bindings panel headings", async () => {
    renderPage();
    expect(await screen.findByText("ผู้ให้บริการ LLM")).toBeInTheDocument();
    expect(await screen.findByText("การผูก LLM")).toBeInTheDocument();
  });

  it("shows the provider Add button but no binding Add button", async () => {
    renderPage();
    expect(await screen.findByText("เพิ่มผู้ให้บริการ")).toBeInTheDocument();
    expect(screen.queryByText("เพิ่มการผูก")).not.toBeInTheDocument();
  });
});
