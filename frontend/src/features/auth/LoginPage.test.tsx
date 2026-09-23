import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { login } from "@/shared/lib/oidc";
import LoginPage from "./LoginPage";

const mockNavigate = vi.fn();
let mockUser: unknown = null;
vi.mock("@/features/auth/useAuth", () => ({
  useAuth: () => ({ user: mockUser, isAdmin: false, isLoading: false }),
}));
vi.mock("@/shared/lib/oidc", () => ({
  login: vi.fn(),
}));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => {
  mockUser = null;
  mockNavigate.mockClear();
  vi.mocked(login).mockClear();
});

describe("LoginPage", () => {
  it("calls login() when the button is clicked", () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /เข้าสู่ระบบ/ }));
    expect(login).toHaveBeenCalledTimes(1);
  });

  it("does not link to the removed signup page", () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link", { name: /สมัครสมาชิก/ })).not.toBeInTheDocument();
  });

  it("links back to the home page", () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: /กลับสู่หน้าหลัก/ });
    expect(link).toHaveAttribute("href", "/");
  });
});
