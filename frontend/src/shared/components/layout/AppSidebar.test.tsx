import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppSidebar } from "./AppSidebar";
import { SidebarProvider } from "@/shared/components/ui/sidebar";
import type { AuthUser } from "@/features/auth/useAuth";

const auth: { user: AuthUser | null; signOut: () => void } = {
  user: null,
  signOut: () => {},
};
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => auth }));
vi.mock("@/features/agencies/useAgencies", () => ({ useAgencies: () => ({ data: [] }) }));

function renderSidebar() {
  return render(
    <MemoryRouter>
      <SidebarProvider>
        <AppSidebar />
      </SidebarProvider>
    </MemoryRouter>,
  );
}

function LocationDisplay() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname + loc.search}</div>;
}

describe("AppSidebar visibility", () => {
  beforeEach(() => {
    auth.user = { id: "1", email: "u@x.com", displayName: "U", role: "user", avatarUrl: null };
  });

  it("shows only chat and architecture for a basic user (no dashboards, no admin pages)", () => {
    auth.user = { ...auth.user!, role: "user" };
    renderSidebar();
    expect(screen.getByText("แชทใหม่")).toBeInTheDocument();
    expect(screen.getByText("Architecture")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
    expect(screen.queryByText("จัดการหน่วยงาน")).not.toBeInTheDocument();
  });

  it("shows read-only operational pages but not admin-only pages for staff", () => {
    auth.user = { ...auth.user!, role: "staff" };
    renderSidebar();
    expect(screen.getByText("แชทใหม่")).toBeInTheDocument();
    expect(screen.getByText("Architecture")).toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("จัดการหน่วยงาน")).not.toBeInTheDocument();
  });

  it("shows every nav item for an admin", () => {
    auth.user = { ...auth.user!, role: "admin" };
    renderSidebar();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("จัดการหน่วยงาน")).toBeInTheDocument();
    expect(screen.getByText("ตั้งค่าระบบ")).toBeInTheDocument();
    expect(screen.queryByText("LLM Settings")).not.toBeInTheDocument();
    expect(screen.queryByText("API Keys")).not.toBeInTheDocument();
    expect(screen.queryByText("จัดการผู้ใช้")).not.toBeInTheDocument();
    expect(screen.queryByText("การใช้งาน API Key")).not.toBeInTheDocument();
    expect(screen.queryByText("ประวัติการเชื่อมต่อ")).not.toBeInTheDocument();
    expect(screen.queryByText("บันทึกการตรวจสอบ")).not.toBeInTheDocument();
  });

  it("no longer shows the removed my-agencies nav item", () => {
    auth.user = { ...auth.user!, role: "admin" };
    renderSidebar();
    expect(screen.queryByText("หน่วยงานของฉัน")).not.toBeInTheDocument();
  });

  it("resets the chat via ?new when แชทใหม่ is clicked while already on /chat", async () => {
    auth.user = { ...auth.user!, role: "admin" };
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <SidebarProvider>
          <AppSidebar />
        </SidebarProvider>
        <LocationDisplay />
      </MemoryRouter>,
    );
    await user.click(screen.getByText("แชทใหม่"));
    expect(screen.getByTestId("loc")).toHaveTextContent("/chat?new=1");
  });
});
