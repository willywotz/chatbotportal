import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LlmRoutesList } from "./LlmRoutesList";
import type { LlmRoute } from "./llmRouteApi";

const route: LlmRoute = {
  id: "1",
  purpose: "classification",
  provider_id: "p1",
  provider_name: "openrouter",
  model: "gpt-x",
  timeout_override: null,
  enabled: true,
};

const noop = vi.fn();

describe("LlmRoutesList", () => {
  it("shows latency on a successful test", () => {
    render(
      <LlmRoutesList
        routes={[route]}
        onEdit={noop}
        onTest={noop}
        testState={{ classification: { loading: false, result: { ok: true, latency_ms: 240, model: "gpt-x", error: null } } }}
      />,
    );
    expect(screen.getByText(/240\s*ms/)).toBeInTheDocument();
  });

  it("shows the error message on a failed test", () => {
    render(
      <LlmRoutesList
        routes={[route]}
        onEdit={noop}
        onTest={noop}
        testState={{ classification: { loading: false, result: { ok: false, latency_ms: 0, model: null, error: "no enabled route" } } }}
      />,
    );
    expect(screen.getByText(/no enabled route/)).toBeInTheDocument();
  });

  it("calls onTest with the purpose when the test button is clicked", async () => {
    const onTest = vi.fn();
    render(<LlmRoutesList routes={[route]} onEdit={noop} onTest={onTest} testState={{}} />);
    await userEvent.click(screen.getByRole("button", { name: "ทดสอบ" }));
    expect(onTest).toHaveBeenCalledWith("classification");
  });
});
