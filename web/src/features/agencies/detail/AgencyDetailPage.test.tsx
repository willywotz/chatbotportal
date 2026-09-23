import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { mockAgencies, resetMockData } from "@/mocks/fixtures";

import AgencyDetailPage from "./AgencyDetailPage";

afterEach(() => {
  resetMockData();
});

const ACTIVE_ID = "11111111-1111-1111-1111-111111111111";
const DRAFT_ID = "33333333-3333-3333-3333-333333333333";

function renderDetail(id: string, search = "") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/agencies/${id}${search}`]}>
        <Routes>
          <Route path="/agencies/:id" element={<AgencyDetailPage />} />
          <Route path="/agencies/:id/setup" element={<div>agency-form</div>} />
          <Route path="/agencies/:id/edit" element={<div>agency-form</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgencyDetailPage", () => {
  it("renders header with status badge and the three tabs (no edit tab)", async () => {
    renderDetail(ACTIVE_ID);
    await waitFor(() => expect(screen.getByText("กรมสรรพากร")).toBeInTheDocument());
    expect(screen.getByText("Active")).toBeInTheDocument();
    for (const tab of ["ภาพรวม", "Health", "Logs"]) {
      expect(screen.getByRole("tab", { name: new RegExp(tab) })).toBeInTheDocument();
    }
    expect(screen.queryByRole("tab", { name: "แก้ไข" })).not.toBeInTheDocument();
  });

  it("links the แก้ไข button to the agency form", async () => {
    renderDetail(ACTIVE_ID);
    await waitFor(() => expect(screen.getByText("กรมสรรพากร")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /แก้ไข/ })).toHaveAttribute(
      "href",
      `/agencies/${ACTIVE_ID}/edit`,
    );
  });

  it("offers only legal transitions in the status dropdown and applies one", async () => {
    const user = userEvent.setup();
    renderDetail(ACTIVE_ID);
    await waitFor(() => expect(screen.getByText("กรมสรรพากร")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /สถานะ/ }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("ปิดปรับปรุง")).toBeInTheDocument();
    expect(within(menu).getByText("ปิดการใช้งาน")).toBeInTheDocument();
    expect(within(menu).queryByText("เปิดใช้งาน")).not.toBeInTheDocument();
    await user.click(within(menu).getByText("ปิดปรับปรุง"));
    await waitFor(() =>
      expect(mockAgencies.find((a) => a.id === ACTIVE_ID)!.status).toBe("maintenance"),
    );
  });

  it("offers direct activation for a draft", async () => {
    const user = userEvent.setup();
    renderDetail(DRAFT_ID);
    await waitFor(() => expect(screen.getByText("กรมที่ดิน")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /สถานะ/ }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("เปิดใช้งาน")).toBeInTheDocument();
    expect(within(menu).getByText("ปิดการใช้งาน")).toBeInTheDocument();
  });

  it("shows a continue-setup banner for drafts", async () => {
    renderDetail(DRAFT_ID);
    await waitFor(() => expect(screen.getByText("กรมที่ดิน")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /ตั้งค่าต่อ/ })).toHaveAttribute(
      "href",
      `/agencies/${DRAFT_ID}/setup`,
    );
  });

  it("shows overview stat cards", async () => {
    renderDetail(ACTIVE_ID);
    await waitFor(() => expect(screen.getByText("กรมสรรพากร")).toBeInTheDocument());
    expect(screen.getByText(/99.2%/)).toBeInTheDocument();
    expect(screen.getByText(/320/)).toBeInTheDocument();
    expect(screen.getByText("1,204")).toBeInTheDocument();
  });
});
