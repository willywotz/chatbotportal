import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "next-themes";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import FeedbackPage from "./FeedbackPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider attribute="class">
        <FeedbackPage />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("FeedbackPage error state", () => {
  it("shows an error alert when the feedback stats endpoint fails", async () => {
    server.use(http.get("*/api/v1/feedback/statistics", () => HttpResponse.error()));
    renderPage();
    // FeedbackSummaryCards shows inline error; QueryStateBoundary shows its own error card
    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0));
    expect(screen.getAllByRole("button", { name: /ลองอีกครั้ง/ }).length).toBeGreaterThan(0);
  });

  it("shows empty state (not error) when stats succeed but totalRatings is 0", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Feedback ทั้งหมด")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("FeedbackPage", () => {
  it("renders summary cards, charts, and low-rated questions from stats", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Feedback ทั้งหมด")).toBeInTheDocument());
    expect(screen.getByText("แนวโน้มความพึงพอใจรายวัน (14 วัน)")).toBeInTheDocument();
    expect(screen.getByText("ความพึงพอใจแยกตามหน่วยงาน")).toBeInTheDocument();
    expect(screen.getByText("คำถามที่ได้คะแนนต่ำ (ล่าสุด)")).toBeInTheDocument();
    expect(screen.getByText("ทำไมระบบตอบช้า")).toBeInTheDocument();
  });
});
