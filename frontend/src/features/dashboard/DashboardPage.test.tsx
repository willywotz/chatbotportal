import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "next-themes";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import DashboardPage from "./DashboardPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider attribute="class">
        <MemoryRouter initialEntries={["/dashboard"]}>
          <DashboardPage />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("DashboardPage error state", () => {
  it("shows an error alert when the dashboard stats endpoint fails", async () => {
    server.use(http.get("*/api/v1/dashboard/statistics", () => HttpResponse.error()));
    renderPage();
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText(/เกิดข้อผิดพลาด/)).toBeInTheDocument();
  });
});

describe("DashboardPage feedback section", () => {
  it("shows the summary cards and a link to the feedback page", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Feedback ทั้งหมด")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /ดูทั้งหมด/ })).toHaveAttribute("href", "/feedback");
  });

  it("no longer renders the full feedback charts or low-rated list heading", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Feedback ทั้งหมด")).toBeInTheDocument());
    expect(screen.queryByText("แนวโน้มความพึงพอใจรายวัน (14 วัน)")).not.toBeInTheDocument();
    expect(screen.queryByText("คำถามที่ได้คะแนนต่ำ (ล่าสุด)")).not.toBeInTheDocument();
  });

  it("shows a preview of recent low-rated questions", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("ทำไมระบบตอบช้า")).toBeInTheDocument());
    expect(screen.getAllByText("กรมสรรพากร").length).toBeGreaterThan(0);
  });
});
