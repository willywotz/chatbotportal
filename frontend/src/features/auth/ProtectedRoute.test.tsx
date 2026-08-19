import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProtectedRoute } from "./ProtectedRoute";
import type { AuthUser } from "@/features/auth/useAuth";

const auth: { user: AuthUser | null; isAdmin: boolean; isLoading: boolean } = {
  user: null,
  isAdmin: false,
  isLoading: false,
};
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => auth }));

function renderAt(initial: string, ui: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/chat" element={<div>chat page</div>} />
        <Route path="/secret" element={ui} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute allowedRoles", () => {
  beforeEach(() => {
    auth.user = { id: "1", email: "u@test.com", displayName: "User", role: "user", avatarUrl: null };
    auth.isAdmin = false;
    auth.isLoading = false;
  });

  it("redirects a role not in allowedRoles to /chat", () => {
    auth.user = { ...auth.user!, role: "user" };
    renderAt("/secret", <ProtectedRoute allowedRoles={["admin"]}><div>secret content</div></ProtectedRoute>);
    expect(screen.getByText("chat page")).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("lets a role in allowedRoles through", () => {
    auth.user = { ...auth.user!, role: "admin" };
    renderAt("/secret", <ProtectedRoute allowedRoles={["admin"]}><div>secret content</div></ProtectedRoute>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("does not gate routes without allowedRoles", () => {
    renderAt("/secret", <ProtectedRoute><div>secret content</div></ProtectedRoute>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("lets staff through a staff+admin route", () => {
    auth.user = { ...auth.user!, role: "staff" };
    renderAt(
      "/secret",
      <ProtectedRoute allowedRoles={["staff", "admin"]}><div>secret content</div></ProtectedRoute>,
    );
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("redirects a plain user off a staff+admin route", () => {
    auth.user = { ...auth.user!, role: "user" };
    renderAt(
      "/secret",
      <ProtectedRoute allowedRoles={["staff", "admin"]}><div>secret content</div></ProtectedRoute>,
    );
    expect(screen.getByText("chat page")).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });
});
