import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/mocks/server";
import AuditLogPage from "./AuditLogPage";

const PAGE_SIZE = 50;

function makeEntries(count: number, startIndex = 0) {
  return Array.from({ length: count }, (_, i) => ({
    id: `entry-${startIndex + i}`,
    actor_id: "user-1",
    actor_email: `actor-${startIndex + i}@example.com`,
    action: "user.create",
    object_type: "user",
    object_id: `obj-${startIndex + i}`,
    detail: null,
    created_at: new Date(2026, 0, startIndex + i + 1).toISOString(),
  }));
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AuditLogPage />
    </QueryClientProvider>,
  );
}

describe("AuditLogPage server pagination", () => {
  it("renders page 1 entries on initial load", async () => {
    server.use(
      http.get("*/api/v1/audit-log/", () =>
        HttpResponse.json({ data: makeEntries(PAGE_SIZE), total: 120 }),
      ),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("actor-0@example.com")).toBeInTheDocument(),
    );
    expect(screen.getByText(/1–50 จาก 120/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ก่อนหน้า/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /ถัดไป/ })).toBeEnabled();
  });

  it("clicking Next advances offset and requests next page from server", async () => {
    const handler = vi.fn();

    server.use(
      http.get("*/api/v1/audit-log/", ({ request }) => {
        const url = new URL(request.url);
        const offset = Number(url.searchParams.get("offset") ?? 0);
        handler(offset);
        const startIndex = offset;
        const remaining = Math.max(0, 120 - offset);
        const count = Math.min(PAGE_SIZE, remaining);
        return HttpResponse.json({ data: makeEntries(count, startIndex), total: 120 });
      }),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("actor-0@example.com")).toBeInTheDocument(),
    );

    expect(handler).toHaveBeenCalledWith(0);

    await userEvent.click(screen.getByRole("button", { name: /ถัดไป/ }));

    await waitFor(() =>
      expect(screen.getByText("actor-50@example.com")).toBeInTheDocument(),
    );

    expect(handler).toHaveBeenCalledWith(50);
    expect(screen.getByText(/51–100 จาก 120/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ก่อนหน้า/ })).toBeEnabled();
  });

  it("clicking Next then Prev returns to page 1", async () => {
    server.use(
      http.get("*/api/v1/audit-log/", ({ request }) => {
        const url = new URL(request.url);
        const offset = Number(url.searchParams.get("offset") ?? 0);
        const startIndex = offset;
        const count = Math.min(PAGE_SIZE, Math.max(0, 120 - offset));
        return HttpResponse.json({ data: makeEntries(count, startIndex), total: 120 });
      }),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("actor-0@example.com")).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await waitFor(() =>
      expect(screen.getByText("actor-50@example.com")).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByRole("button", { name: /ก่อนหน้า/ }));
    await waitFor(() =>
      expect(screen.getByText("actor-0@example.com")).toBeInTheDocument(),
    );

    expect(screen.getByText(/1–50 จาก 120/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ก่อนหน้า/ })).toBeDisabled();
  });

  it("Next button disabled on last page", async () => {
    server.use(
      http.get("*/api/v1/audit-log/", ({ request }) => {
        const url = new URL(request.url);
        const offset = Number(url.searchParams.get("offset") ?? 0);
        const startIndex = offset;
        const count = Math.min(PAGE_SIZE, Math.max(0, 120 - offset));
        return HttpResponse.json({ data: makeEntries(count, startIndex), total: 120 });
      }),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /ถัดไป/ })).toBeEnabled(),
    );

    // Advance to page 3 (offset=100, last page since 120 total)
    await userEvent.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await waitFor(() =>
      expect(screen.getByText("actor-50@example.com")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await waitFor(() =>
      expect(screen.getByText("actor-100@example.com")).toBeInTheDocument(),
    );

    expect(screen.getByText(/101–120 จาก 120/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ถัดไป/ })).toBeDisabled();
  });

  it("changing a filter resets to page 1", async () => {
    const handler = vi.fn();

    server.use(
      http.get("*/api/v1/audit-log/", ({ request }) => {
        const url = new URL(request.url);
        const offset = Number(url.searchParams.get("offset") ?? 0);
        handler(offset);
        const count = Math.min(PAGE_SIZE, Math.max(0, 120 - offset));
        return HttpResponse.json({ data: makeEntries(count, offset), total: 120 });
      }),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /ถัดไป/ })).toBeEnabled(),
    );

    await userEvent.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await waitFor(() =>
      expect(screen.getByText("actor-50@example.com")).toBeInTheDocument(),
    );

    const calls = handler.mock.calls.length;
    await userEvent.type(screen.getByPlaceholderText(/ค้นหาอีเมลผู้กระทำ/), "a");

    await waitFor(() =>
      expect(handler.mock.calls.length).toBeGreaterThan(calls),
    );

    const lastOffset = handler.mock.calls[handler.mock.calls.length - 1][0];
    expect(lastOffset).toBe(0);
  });
});
