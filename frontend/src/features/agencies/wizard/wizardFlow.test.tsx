import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { mockAgencies, resetMockData } from "@/mocks/fixtures";

import AgencyWizardPage from "./AgencyWizardPage";

afterEach(() => {
  resetMockData();
});

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/agencies/new"]}>
        <Routes>
          <Route path="/agencies/new" element={<AgencyWizardPage />} />
          <Route path="/agencies/:id" element={<div>detail-page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("wizard connection step — URL validation", () => {
  it("keeps ถัดไป disabled when URL is invalid", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("ชื่อหน่วยงาน"), "ทดสอบ");
    await user.type(screen.getByLabelText("ชื่อย่อ"), "ทส.");
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));

    // On connection step — type an invalid URL (no scheme)
    await user.type(screen.getByLabelText("Endpoint URL"), "not-a-url");
    // ถัดไป must be disabled for an invalid URL
    expect(screen.getByRole("button", { name: /ถัดไป/ })).toBeDisabled();
  });

  it("enables ถัดไป once a valid URL is entered", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("ชื่อหน่วยงาน"), "ทดสอบ2");
    await user.type(screen.getByLabelText("ชื่อย่อ"), "ทส2.");
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));

    await user.type(screen.getByLabelText("Endpoint URL"), "https://valid.example/api");
    expect(screen.getByRole("button", { name: /ถัดไป/ })).not.toBeDisabled();
  });
});

describe("wizard full flow (API agency)", () => {
  it("creates an active agency through all five steps", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("ชื่อหน่วยงาน"), "กรมศุลกากร");
    await user.type(screen.getByLabelText("ชื่อย่อ"), "ศก.");
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));

    await user.type(screen.getByLabelText("Endpoint URL"), "https://customs.example/api/chat");
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));

    await waitFor(() => expect(mockAgencies.some((a) => a.name === "กรมศุลกากร")).toBe(true));
    const created = mockAgencies.find((a) => a.name === "กรมศุลกากร")!;
    expect(created.status).toBe("draft");

    // Step 3 — test: run the conformance battery (required before activation)
    await user.click(screen.getByRole("button", { name: /รันชุดทดสอบ Conformance/ }));
    await waitFor(() => expect(screen.getByText(/ผ่านการทดสอบ Conformance/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));

    await user.type(screen.getByLabelText(/Router hint/), "คำถามภาษีนำเข้า");
    await user.type(screen.getByLabelText(/Priority/), "2");
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));

    expect(screen.getByText("กรมศุลกากร")).toBeInTheDocument();
    expect(screen.getByText("https://customs.example/api/chat")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /เปิดใช้งาน/ }));

    await waitFor(() => expect(screen.getByText("detail-page")).toBeInTheDocument());
    const final = mockAgencies.find((a) => a.name === "กรมศุลกากร")!;
    expect(final.status).toBe("active");
    expect(final.router_hint).toBe("คำถามภาษีนำเข้า");
    expect(final.priority).toBe(2);
  });

  it("keeps เปิดใช้งาน disabled on review until conformance passes", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("ชื่อหน่วยงาน"), "กรมที่ดิน");
    await user.type(screen.getByLabelText("ชื่อย่อ"), "ทด.");
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await user.type(screen.getByLabelText("Endpoint URL"), "https://land.example/api");
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));

    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));

    // Review: activation is blocked until the conformance battery passes
    expect(screen.getByRole("button", { name: /เปิดใช้งาน/ })).toBeDisabled();
    expect(screen.getByText(/ต้องรันชุดทดสอบ Conformance/)).toBeInTheDocument();
  });

  it("saves as draft from the review step", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.type(screen.getByLabelText("ชื่อหน่วยงาน"), "กรมป่าไม้");
    await user.type(screen.getByLabelText("ชื่อย่อ"), "ปม.");
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await user.type(screen.getByLabelText("Endpoint URL"), "https://forest.example/api");
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await user.click(screen.getByRole("button", { name: /ถัดไป/ }));
    await user.click(screen.getByRole("button", { name: /บันทึกเป็น Draft/ }));

    await waitFor(() => expect(screen.getByText("detail-page")).toBeInTheDocument());
    expect(mockAgencies.find((a) => a.name === "กรมป่าไม้")!.status).toBe("draft");
  });
});
