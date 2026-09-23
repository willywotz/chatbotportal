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
