import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { mapRowToAgency } from "@/shared/types/agency";
import { makeFixtureAgencies } from "@/mocks/fixtures";

import { AgencyCard } from "./AgencyCard";

const agencies = makeFixtureAgencies().map(mapRowToAgency);
const active = agencies.find((a) => a.status === "active")!;
const draft = agencies.find((a) => a.status === "draft")!;
const disabled = agencies.find((a) => a.status === "disabled")!;
const maintenance = agencies.find((a) => a.status === "maintenance")!;

const noop = vi.fn();

function renderCard(agency: typeof active) {
  return render(
    <MemoryRouter>
      <AgencyCard agency={agency} onTest={noop} onDelete={noop} onStatusChange={noop} testing={false} testResult={null} />
    </MemoryRouter>,
  );
}

describe("AgencyCard write controls", () => {
  it("renders the actions menu for a writer", () => {
    render(
      <MemoryRouter>
        <AgencyCard agency={active} onTest={noop} onDelete={noop} onStatusChange={noop} testing={false} testResult={null} />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText("actions")).toBeInTheDocument();
  });
});

describe("AgencyCard", () => {
  it("shows health stats for an active agency", () => {
    renderCard(active);
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText(/99.2%/)).toBeInTheDocument();
    expect(screen.getByText(/320\s*ms/)).toBeInTheDocument();
    expect(screen.getByText(/P1/)).toBeInTheDocument();
  });

  it("shows a continue-setup link for a draft", () => {
    renderCard(draft);
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ตั้งค่าต่อ/ })).toHaveAttribute(
      "href",
      `/agencies/${draft.id}/setup`,
    );
    expect(screen.queryByText(/uptime/i)).not.toBeInTheDocument();
  });

  it("mutes a disabled agency and hides health", () => {
    const { container } = renderCard(disabled);
    expect(screen.getByText("Disabled")).toBeInTheDocument();
    expect(container.firstElementChild?.className).toContain("opacity-60");
  });

  it("marks maintenance with the expected-downtime badge but keeps health", () => {
    renderCard(maintenance);
    expect(screen.getByText("ปิดปรับปรุง")).toBeInTheDocument();
    expect(screen.getByText(/12.5%/)).toBeInTheDocument();
  });

  it("navigates to the edit tab when choosing แก้ไข from the menu", async () => {
    const user = userEvent.setup();
    function LocationProbe() {
      const location = useLocation();
      return <div data-testid="location">{location.pathname}{location.search}</div>;
    }
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={<AgencyCard agency={active} onTest={noop} onDelete={noop} onStatusChange={noop} testing={false} testResult={null} />}
          />
          <Route path="/agencies/:id" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    );
    await user.click(screen.getByLabelText("actions"));
    await user.click(screen.getByText("แก้ไข"));
    expect(await screen.findByTestId("location")).toHaveTextContent(`/agencies/${active.id}?tab=edit`);
  });
});
