import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { api } from "@/shared/lib/apiClient";
import LoginPage from "./LoginPage";

const setAuth = vi.fn();
const mockNavigate = vi.fn();
let mockUser: unknown = null;
vi.mock("@/features/auth/useAuth", () => ({
  useAuth: () => ({ user: mockUser, isAdmin: false, isLoading: false, setAuth }),
}));
vi.mock("@/shared/lib/apiClient", () => ({
  api: { post: vi.fn() },
}));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => {
  mockUser = null;
  mockNavigate.mockClear();
});

describe("LoginPage", () => {
  it("logs in with only the user (no access_token) and calls setAuth", async () => {
    const user = { id: "1", email: "a@b.co", displayName: "A", role: "admin", avatarUrl: null };
    vi.mocked(api.post).mockResolvedValueOnce({ user });
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("อีเมล"), { target: { value: "a@b.co" } });
    fireEvent.change(screen.getByLabelText("รหัสผ่าน"), { target: { value: "pw12345" } });
    fireEvent.click(screen.getByRole("button", { name: /เข้าสู่ระบบ/ }));
    await waitFor(() => expect(setAuth).toHaveBeenCalledWith(user));
    expect(api.post).toHaveBeenCalledWith("/api/v1/authentication/login", { email: "a@b.co", password: "pw12345" });
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

  it("does not redirect an anonymous (isEphemeral) user to /chat", () => {
    mockUser = { id: "1", email: "anon@ephemeral.local", displayName: "", role: "user", avatarUrl: null, isEphemeral: true };
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /เข้าสู่ระบบ/ })).toBeInTheDocument();
  });
});
