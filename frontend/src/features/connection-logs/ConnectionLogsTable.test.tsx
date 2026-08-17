import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import ConnectionLogsPage from "./ConnectionLogsPage";

const EMPTY_LOGS = {
  search: null,
  page: 1,
  page_size: 20,
  items: [],
  total_items: 0,
  total_connections: 0,
  successful_connections: 0,
  failed_connections: 0,
  average_latency_ms: 0,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConnectionLogsPage />
    </QueryClientProvider>,
  );
}

describe("ConnectionLogsTable error state", () => {
  it("shows an error alert row when the connection-logs endpoint fails", async () => {
    server.use(
      http.get("*/api/v1/connection-logs", () => HttpResponse.error()),
      http.get("*/api/v1/connection-logs/info", () => HttpResponse.json({})),
    );
    renderPage();
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText(/เกิดข้อผิดพลาด/)).toBeInTheDocument();
  });

  it("shows a retry button in the error row and clicking it triggers a refetch", async () => {
    server.use(
      http.get("*/api/v1/connection-logs", () => HttpResponse.error()),
      http.get("*/api/v1/connection-logs/info", () => HttpResponse.json({})),
    );
    renderPage();
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

    const retryBtn = screen.getByRole("button", { name: /ลองอีกครั้ง/ });
    expect(retryBtn).toBeInTheDocument();

    server.use(http.get("*/api/v1/connection-logs", () => HttpResponse.json(EMPTY_LOGS)));
    await userEvent.click(retryBtn);

    await waitFor(() => expect(screen.getByText("ไม่พบข้อมูล")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows empty row (not error) when fetch succeeds but no logs", async () => {
    server.use(
      http.get("*/api/v1/connection-logs", () => HttpResponse.json(EMPTY_LOGS)),
      http.get("*/api/v1/connection-logs/info", () => HttpResponse.json({})),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("ไม่พบข้อมูล")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("ConnectionLogs test-action toggle", () => {
  it("omits include_test by default and requests include_test=true when toggled", async () => {
    const urls: string[] = [];
    server.use(
      http.get("*/api/v1/connection-logs", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json(EMPTY_LOGS);
      }),
      http.get("*/api/v1/connection-logs/info", () => HttpResponse.json({})),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("ไม่พบข้อมูล")).toBeInTheDocument());
    expect(urls.every((u) => !u.includes("include_test=true"))).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "แสดงการทดสอบ" }));
    await waitFor(() =>
      expect(urls.some((u) => u.includes("include_test=true"))).toBe(true),
    );
  });
});
