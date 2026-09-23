import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_FORM_STATE, type AgencyFormState } from "../agencyForm";
import { StepConnection } from "./StepConnection";

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("StepConnection", () => {
  it("shows API fields for API type", () => {
    const form: AgencyFormState = { ...DEFAULT_FORM_STATE, connectionType: "API" };
    render(wrap(<StepConnection form={form} patch={vi.fn()} />));
    expect(screen.getByLabelText("Endpoint URL")).toBeInTheDocument();
    expect(screen.getByLabelText(/Expected payload/)).toBeInTheDocument();
    expect(screen.getByText(/Headers/)).toBeInTheDocument();
  });

  it("shows only endpoint for A2A", () => {
    const form: AgencyFormState = { ...DEFAULT_FORM_STATE, connectionType: "A2A" };
    render(wrap(<StepConnection form={form} patch={vi.fn()} />));
    expect(screen.getByLabelText("Endpoint URL")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Expected payload/)).not.toBeInTheDocument();
  });

  it("discovers MCP tools and selects one", async () => {
    const patch = vi.fn();
    const form: AgencyFormState = {
      ...DEFAULT_FORM_STATE,
      connectionType: "MCP",
      endpointUrl: "https://mcp.example/sse",
    };
    render(wrap(<StepConnection form={form} patch={patch} />));
    await userEvent.click(screen.getByRole("button", { name: /Discover tools/ }));
    await waitFor(() => expect(screen.getByText("chat_with_fda")).toBeInTheDocument());
    await userEvent.click(screen.getByText("chat_with_fda"));
    expect(patch).toHaveBeenCalledWith({ mcpToolName: "chat_with_fda" });
  });

  it("switches connection type via patch", async () => {
    const patch = vi.fn();
    render(wrap(<StepConnection form={DEFAULT_FORM_STATE} patch={patch} />));
    await userEvent.click(screen.getByRole("button", { name: "MCP" }));
    expect(patch).toHaveBeenCalledWith({ connectionType: "MCP" });
  });

  it("shows URL error message when endpoint URL is invalid", () => {
    const form: AgencyFormState = { ...DEFAULT_FORM_STATE, endpointUrl: "not-a-valid-url" };
    render(wrap(<StepConnection form={form} patch={vi.fn()} />));
    expect(screen.getByText("URL ไม่ถูกต้อง")).toBeInTheDocument();
  });

  it("does not show URL error message when endpoint URL is empty", () => {
    const form: AgencyFormState = { ...DEFAULT_FORM_STATE, endpointUrl: "" };
    render(wrap(<StepConnection form={form} patch={vi.fn()} />));
    expect(screen.queryByText("URL ไม่ถูกต้อง")).not.toBeInTheDocument();
  });

  it("does not show URL error message when endpoint URL is valid", () => {
    const form: AgencyFormState = { ...DEFAULT_FORM_STATE, endpointUrl: "https://api.example.com" };
    render(wrap(<StepConnection form={form} patch={vi.fn()} />));
    expect(screen.queryByText("URL ไม่ถูกต้อง")).not.toBeInTheDocument();
  });

  it("shows header error message when a header has a value but no name (API type)", () => {
    const form: AgencyFormState = {
      ...DEFAULT_FORM_STATE,
      connectionType: "API",
      apiHeaders: [{ name: "", value: "bearer-token" }],
    };
    render(wrap(<StepConnection form={form} patch={vi.fn()} />));
    expect(screen.getAllByText("กรุณากรอก Header name และ Value ให้ครบ").length).toBeGreaterThan(0);
  });

  it("does not show header error message for entirely empty rows (API type)", () => {
    const form: AgencyFormState = {
      ...DEFAULT_FORM_STATE,
      connectionType: "API",
      apiHeaders: [{ name: "", value: "" }],
    };
    render(wrap(<StepConnection form={form} patch={vi.fn()} />));
    expect(screen.queryByText("กรุณากรอก Header name และ Value ให้ครบ")).not.toBeInTheDocument();
  });
});
