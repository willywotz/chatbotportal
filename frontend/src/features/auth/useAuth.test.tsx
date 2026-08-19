import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/shared/lib/apiClient";
import { keycloak, logout } from "@/shared/lib/keycloak";
import { AuthProvider, useAuth, type AuthUser } from "./useAuth";

vi.mock("@/shared/lib/apiClient", () => ({
  api: { get: vi.fn() },
}));

vi.mock("@/shared/lib/keycloak", () => ({
  keycloak: { authenticated: false },
  logout: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  keycloak.authenticated = false;
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
  it("loads the user from GET /api/v1/authentication/me when keycloak.authenticated is true", async () => {
    keycloak.authenticated = true;
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

  it("sets user to null without calling /me when keycloak.authenticated is false", async () => {
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
    keycloak.authenticated = true;
    vi.mocked(api.get).mockRejectedValueOnce(new Error("401"));
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("loading:false")).toBeInTheDocument());
    expect(screen.getByText("user:none")).toBeInTheDocument();
  });

  it("signOut calls keycloak logout()", async () => {
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
