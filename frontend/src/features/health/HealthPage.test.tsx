import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import HealthPage from "./HealthPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <HealthPage />
    </QueryClientProvider>,
  );
}

describe("HealthPage error and retry", () => {
  it("shows the success content when the API responds normally", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Agency Health Monitoring")).toBeInTheDocument(),
    );
  });

  it("shows the error card with role=alert when the API fails", async () => {
    server.use(
      http.get("*/api/v1/agency-health", () => HttpResponse.error()),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("alert")).toBeInTheDocument(),
    );
    expect(screen.getByText("ไม่สามารถโหลดข้อมูลได้")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ลองอีกครั้ง/ })).toBeInTheDocument();
  });

  it("shows success content after clicking retry when the API recovers", async () => {
    server.use(
      http.get("*/api/v1/agency-health", () => HttpResponse.error()),
    );
    renderPage();

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

    server.resetHandlers();

    await userEvent.click(screen.getByRole("button", { name: /ลองอีกครั้ง/ }));

    await waitFor(() =>
      expect(screen.getByText("Agency Health Monitoring")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
