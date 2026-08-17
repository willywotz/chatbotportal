import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import { FeedbackSummaryCards } from "./FeedbackSummaryCards";

function renderCards() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FeedbackSummaryCards />
    </QueryClientProvider>,
  );
}

describe("FeedbackSummaryCards", () => {
  it("renders the four summary values from stats", async () => {
    renderCards();
    await waitFor(() => expect(screen.getByText("Feedback ทั้งหมด")).toBeInTheDocument());
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("71%")).toBeInTheDocument();
  });

  it("shows an error alert (not skeletons) when the feedback-stats fetch fails", async () => {
    server.use(
      http.get("*/api/v1/feedback/stats", () => HttpResponse.error()),
    );
    renderCards();
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText("Feedback ทั้งหมด")).not.toBeInTheDocument();
  });
});
