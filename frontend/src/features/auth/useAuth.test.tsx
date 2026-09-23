import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/shared/lib/apiClient";
import { isAuthenticated, logout } from "@/shared/lib/oidc";
import { AuthProvider, useAuth, type AuthUser } from "./useAuth";

vi.mock("@/shared/lib/apiClient", () => ({
  api: { get: vi.fn() },
}));

vi.mock("@/shared/lib/oidc", () => ({
  isAuthenticated: vi.fn().mockReturnValue(false),
  logout: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(isAuthenticated).mockReturnValue(false);
});

// The backend returns the principal fields flat and snake_case (see
// routers/auth.py): { id, email, display_name, role }.
const mePayload = { id: "1", email: "a@b.co", display_name: "A", role: "admin" };
const authUser: AuthUser = {
  id: "1",
  email: "a@b.co",
  displayName: "A",
  role: "admin",
  avatarUrl: null,
};

function Consumer() {
  const { user, isAdmin, isLoading, signOut } = useAuth();
  return (
    <div>
      <span>loading:{String(isLoading)}</span>
      <span>user:{user?.email ?? "none"}</span>
      <span>admin:{String(isAdmin)}</span>
      <button onClick={() => signOut()}>signout</button>
    </div>
  );
}

describe("AuthProvider", () => {
  it("loads the user from GET /api/v1/authentication/me when a session exists", async () => {
    vi.mocked(isAuthenticated).mockReturnValue(true);
    vi.mocked(api.get).mockResolvedValueOnce(mePayload);
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("loading:false")).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith("/api/v1/authentication/me");
    expect(screen.getByText(`user:${authUser.email}`)).toBeInTheDocument();
    expect(screen.getByText("admin:true")).toBeInTheDocument();
  });

  it("sets user to null without calling /me when no session exists", async () => {
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("loading:false")).toBeInTheDocument());
    expect(api.get).not.toHaveBeenCalled();
    expect(screen.getByText("user:none")).toBeInTheDocument();
  });

  it("sets user to null when /me fails", async () => {
    vi.mocked(isAuthenticated).mockReturnValue(true);
    vi.mocked(api.get).mockRejectedValueOnce(new Error("401"));
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("loading:false")).toBeInTheDocument());
    expect(screen.getByText("user:none")).toBeInTheDocument();
  });

  it("signOut calls logout()", async () => {
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("loading:false")).toBeInTheDocument());
    await act(async () => screen.getByText("signout").click());
    expect(logout).toHaveBeenCalled();
  });
});
