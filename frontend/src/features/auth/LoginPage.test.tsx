import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import LoginPage from "./LoginPage";

const mockNavigate = vi.fn();
const auth: {
  user: unknown;
  isAdmin: boolean;
  isLoading: boolean;
  signIn: ReturnType<typeof vi.fn>;
  signOut: ReturnType<typeof vi.fn>;
} = { user: null, isAdmin: false, isLoading: false, signIn: vi.fn(), signOut: vi.fn() };

vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => auth }));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => {
  auth.user = null;
  mockNavigate.mockClear();
  auth.signIn.mockClear();
});

describe("LoginPage", () => {
  it("calls signIn() when the button is clicked", () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /เข้าสู่ระบบ/ }));
    expect(auth.signIn).toHaveBeenCalledTimes(1);
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
