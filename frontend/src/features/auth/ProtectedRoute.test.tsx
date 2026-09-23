import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProtectedRoute } from "./ProtectedRoute";
import type { AuthUser } from "@/features/auth/useAuth";

const auth: {
  user: AuthUser | null;
  isAdmin: boolean;
  isLoading: boolean;
  signIn: ReturnType<typeof vi.fn>;
  signOut: ReturnType<typeof vi.fn>;
} = {
  user: null,
  isAdmin: false,
  isLoading: false,
  signIn: vi.fn(),
  signOut: vi.fn(),
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

describe("ProtectedRoute", () => {
  beforeEach(() => {
    auth.user = { id: "1", email: "u@test.com", displayName: "User", role: "user", avatarUrl: null };
    auth.isAdmin = false;
    auth.isLoading = false;
    auth.signIn.mockClear();
  });

  it("redirects to OIDC login when unauthenticated", () => {
    auth.user = null;
    renderAt("/secret", <ProtectedRoute><div>secret content</div></ProtectedRoute>);
    expect(auth.signIn).toHaveBeenCalledWith(window.location.pathname + window.location.search);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    renderAt("/secret", <ProtectedRoute><div>secret content</div></ProtectedRoute>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
    expect(auth.signIn).not.toHaveBeenCalled();
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
