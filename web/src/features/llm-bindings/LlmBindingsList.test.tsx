import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LlmBindingsList } from "./LlmBindingsList";
import type { LlmBinding } from "./llmBindingApi";

const binding: LlmBinding = {
  id: "1",
  purpose: "classification",
  provider_id: "p1",
  provider_name: "openrouter",
  model: "gpt-x",
  model_override: null,
  timeout_override: null,
  enabled: true,
};

const noop = vi.fn();

describe("LlmBindingsList", () => {
  it("shows latency on a successful test", () => {
    render(
      <LlmBindingsList
        bindings={[binding]}
        onEdit={noop}
        onTest={noop}
        testState={{ classification: { loading: false, result: { ok: true, latency_ms: 240, model: "gpt-x", error: null } } }}
      />,
    );
    expect(screen.getByText(/240\s*ms/)).toBeInTheDocument();
  });

  it("shows the error message on a failed test", () => {
    render(
      <LlmBindingsList
        bindings={[binding]}
        onEdit={noop}
        onTest={noop}
        testState={{ classification: { loading: false, result: { ok: false, latency_ms: 0, model: null, error: "no enabled binding" } } }}
      />,
    );
    expect(screen.getByText(/no enabled binding/)).toBeInTheDocument();
  });

  it("calls onTest with the purpose when the test button is clicked", async () => {
    const onTest = vi.fn();
    render(<LlmBindingsList bindings={[binding]} onEdit={noop} onTest={onTest} testState={{}} />);
    await userEvent.click(screen.getByRole("button", { name: "ทดสอบ" }));
    expect(onTest).toHaveBeenCalledWith("classification");
  });
});
