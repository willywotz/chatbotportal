import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import SettingsLayout, { SettingsIndexRedirect } from "./SettingsLayout";

const mockUseAuth = vi.fn();
vi.mock("@/features/auth/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/chat" element={<div>CHAT PAGE</div>} />
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<SettingsIndexRedirect />} />
          <Route path="system" element={<div>SYSTEM PANEL</div>} />
          <Route path="usage" element={<div>USAGE PANEL</div>} />
          <Route path="audit" element={<div>AUDIT PANEL</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("SettingsLayout", () => {
  it("shows all six tabs for an admin", () => {
    mockUseAuth.mockReturnValue({ user: { role: "admin" }, isAdmin: true });
    renderAt("/settings/system");
    for (const label of [
      "ตั้งค่าระบบ",
      "LLM",
      "จัดการผู้ใช้",
      "การใช้งาน",
      "ประวัติการเชื่อมต่อ",
      "บันทึกการตรวจสอบ",
    ]) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
  });

  it("shows only the Usage tab for staff", () => {
    mockUseAuth.mockReturnValue({ user: { role: "staff" }, isAdmin: false });
    renderAt("/settings/usage");
    expect(screen.getByRole("tab", { name: "การใช้งาน" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "จัดการผู้ใช้" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "บันทึกการตรวจสอบ" })).not.toBeInTheDocument();
  });

  it("marks the tab matching the URL as active", () => {
    mockUseAuth.mockReturnValue({ user: { role: "admin" }, isAdmin: true });
    renderAt("/settings/audit");
    expect(screen.getByRole("tab", { name: "บันทึกการตรวจสอบ" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });

  it("redirects the index to the system tab for an admin", () => {
    mockUseAuth.mockReturnValue({ user: { role: "admin" }, isAdmin: true });
    renderAt("/settings");
    expect(screen.getByText("SYSTEM PANEL")).toBeInTheDocument();
  });

  it("redirects the index to the usage tab for staff", () => {
    mockUseAuth.mockReturnValue({ user: { role: "staff" }, isAdmin: false });
    renderAt("/settings");
    expect(screen.getByText("USAGE PANEL")).toBeInTheDocument();
  });

  it("redirects the index to chat for a plain user (no settings tab)", () => {
    mockUseAuth.mockReturnValue({ user: { role: "user" }, isAdmin: false });
    renderAt("/settings");
    expect(screen.getByText("CHAT PAGE")).toBeInTheDocument();
  });
});
