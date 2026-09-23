import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { resetMockData } from "@/mocks/fixtures";

import AgencyWizardPage from "./AgencyWizardPage";

afterEach(() => {
  resetMockData();
});

function renderWizard(initialEntry = "/agencies/new") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/agencies/new" element={<AgencyWizardPage />} />
          <Route path="/agencies/:id/setup" element={<AgencyWizardPage />} />
          <Route path="/agencies/:id" element={<div>detail-page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgencyWizardPage scaffold", () => {
  it("renders the five-step sidebar starting on ข้อมูลทั่วไป", () => {
    renderWizard();
    expect(screen.getByText("ข้อมูลทั่วไป")).toBeInTheDocument();
    expect(screen.getByText("การเชื่อมต่อ")).toBeInTheDocument();
    expect(screen.getByText("สรุป")).toBeInTheDocument();
    expect(screen.getByLabelText("ชื่อหน่วยงาน")).toBeInTheDocument();
  });

  it("blocks ถัดไป until general step is valid", async () => {
    renderWizard();
    expect(screen.getByRole("button", { name: /ถัดไป/ })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("ชื่อหน่วยงาน"), "กรมทดสอบ");
    await userEvent.type(screen.getByLabelText("ชื่อย่อ"), "TST");
    expect(screen.getByRole("button", { name: /ถัดไป/ })).toBeEnabled();
  });

  it("resumes a draft at its first incomplete step", async () => {
    // Fixture draft 333… has name+shortName but no endpoint → connection step.
    renderWizard("/agencies/33333333-3333-3333-3333-333333333333/setup");
    await waitFor(() => expect(screen.getByLabelText("Endpoint URL")).toBeInTheDocument());
  });
});
