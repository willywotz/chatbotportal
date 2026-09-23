import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { mockAgencies, resetMockData } from "@/mocks/fixtures";

import AgencyFormPage from "./AgencyFormPage";

afterEach(() => {
  resetMockData();
});

function renderForm(initialEntry = "/agencies/new") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/agencies/new" element={<AgencyFormPage />} />
          <Route path="/agencies/:id/setup" element={<AgencyFormPage />} />
          <Route path="/agencies/:id/edit" element={<AgencyFormPage />} />
          <Route path="/agencies/:id" element={<div>detail-page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgencyFormPage — single page", () => {
  it("shows general, connection and routing fields together on one page", () => {
    renderForm();
    expect(screen.getByLabelText("ชื่อหน่วยงาน")).toBeInTheDocument();
    expect(screen.getByLabelText("Endpoint URL")).toBeInTheDocument();
    expect(screen.getByLabelText(/Router hint/)).toBeInTheDocument();
  });

  it("does not render a step sidebar", () => {
    renderForm();
    expect(screen.queryByText("สรุป")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /ถัดไป/ })).not.toBeInTheDocument();
  });

  it("keeps บันทึก Draft disabled until name and shortName are filled", async () => {
    const user = userEvent.setup();
    renderForm();
    expect(screen.getByRole("button", { name: /บันทึก Draft/ })).toBeDisabled();
    await user.type(screen.getByLabelText("ชื่อหน่วยงาน"), "กรมทดสอบ");
    await user.type(screen.getByLabelText("ชื่อย่อ"), "TST");
    expect(screen.getByRole("button", { name: /บันทึก Draft/ })).toBeEnabled();
  });

  it("keeps เปิดใช้งาน disabled until an endpoint URL is valid", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText("ชื่อหน่วยงาน"), "กรมทดสอบ");
    await user.type(screen.getByLabelText("ชื่อย่อ"), "TST");
    expect(screen.getByRole("button", { name: /เปิดใช้งาน/ })).toBeDisabled();
    await user.type(screen.getByLabelText("Endpoint URL"), "https://valid.example/api");
    expect(screen.getByRole("button", { name: /เปิดใช้งาน/ })).toBeEnabled();
  });
});

describe("AgencyFormPage — create flow (API agency)", () => {
  it("creates an active agency with routing details in one submit", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText("ชื่อหน่วยงาน"), "กรมศุลกากร");
    await user.type(screen.getByLabelText("ชื่อย่อ"), "ศก.");
    await user.type(screen.getByLabelText("Endpoint URL"), "https://customs.example/api/chat");
    await user.type(screen.getByLabelText(/Router hint/), "คำถามภาษีนำเข้า");
    await user.type(screen.getByLabelText(/Priority/), "2");

    await user.click(screen.getByRole("button", { name: /เปิดใช้งาน/ }));

    await waitFor(() => expect(screen.getByText("detail-page")).toBeInTheDocument());
    const final = mockAgencies.find((a) => a.name === "กรมศุลกากร")!;
    expect(final.status).toBe("active");
    expect(final.router_hint).toBe("คำถามภาษีนำเข้า");
    expect(final.priority).toBe(2);
  });

  it("saves a draft without activating", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText("ชื่อหน่วยงาน"), "กรมป่าไม้");
    await user.type(screen.getByLabelText("ชื่อย่อ"), "ปม.");
    await user.type(screen.getByLabelText("Endpoint URL"), "https://forest.example/api");
    await user.click(screen.getByRole("button", { name: /บันทึก Draft/ }));

    await waitFor(() => expect(screen.getByText("detail-page")).toBeInTheDocument());
    expect(mockAgencies.find((a) => a.name === "กรมป่าไม้")!.status).toBe("draft");
  });
});

describe("AgencyFormPage — resume a draft", () => {
  it("hydrates the form from an existing draft", async () => {
    renderForm("/agencies/33333333-3333-3333-3333-333333333333/setup");
    await waitFor(() =>
      expect(screen.getByLabelText("ชื่อหน่วยงาน")).toHaveValue("กรมที่ดิน"),
    );
  });
});

describe("AgencyFormPage — edit an existing agency", () => {
  it("hydrates the form from the agency on the edit route", async () => {
    renderForm("/agencies/11111111-1111-1111-1111-111111111111/edit");
    await waitFor(() =>
      expect(screen.getByLabelText("ชื่อหน่วยงาน")).toHaveValue("กรมสรรพากร"),
    );
  });
});
