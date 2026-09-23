import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { resetMockData } from "@/mocks/fixtures";
import { server } from "@/mocks/server";

import { HealthTab } from "./HealthTab";

afterEach(() => {
  resetMockData();
});

const ACTIVE_ID = "11111111-1111-1111-1111-111111111111";

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("HealthTab", () => {
  it("renders uptime and latency charts for the default 24h window", async () => {
    render(wrap(<HealthTab agencyId={ACTIVE_ID} />));
    await waitFor(() => expect(screen.getByText(/Uptime/)).toBeInTheDocument());
    expect(screen.getByText(/Latency/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "24h" })).toBeInTheDocument();
  });

  it("switches window", async () => {
    render(wrap(<HealthTab agencyId={ACTIVE_ID} />));
    await waitFor(() => expect(screen.getByText(/Uptime/)).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "7d" }));
    expect(screen.getByRole("button", { name: "7d" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows an error state with retry when history fails", async () => {
    server.use(
      http.get("*/api/v1/agencies/:id/health/history", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    render(wrap(<HealthTab agencyId={ACTIVE_ID} />));
    await waitFor(() => expect(screen.getByText(/โหลดข้อมูลไม่สำเร็จ/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /ลองใหม่/ })).toBeInTheDocument();
  });
});
