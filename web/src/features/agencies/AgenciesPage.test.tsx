import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { resetMockData } from "@/mocks/fixtures";

import AgenciesPage from "./AgenciesPage";

afterEach(() => {
  resetMockData();
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/agencies"]}>
        <AgenciesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgenciesPage", () => {
  it("renders all fixture agencies as tiles", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("กรมสรรพากร")).toBeInTheDocument());
    expect(screen.getByText("กรมที่ดิน")).toBeInTheDocument();
    expect(screen.getByText("กรมขนส่งทางบก")).toBeInTheDocument();
  });

  it("filters by lifecycle state", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("กรมสรรพากร")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Draft" }));
    expect(screen.getByText("กรมที่ดิน")).toBeInTheDocument();
    expect(screen.queryByText("กรมสรรพากร")).not.toBeInTheDocument();
  });

  it("filters by search text", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("กรมสรรพากร")).toBeInTheDocument());
    await userEvent.type(screen.getByPlaceholderText(/ค้นหา/), "ขนส่ง");
    expect(screen.getByText("กรมขนส่งทางบก")).toBeInTheDocument();
    expect(screen.queryByText("กรมสรรพากร")).not.toBeInTheDocument();
  });

  it("links the add button to the wizard", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("กรมสรรพากร")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /เพิ่มหน่วยงาน/ })).toHaveAttribute("href", "/agencies/new");
  });
});
