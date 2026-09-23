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
  purpose: "classification",
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
