import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/shared/lib/apiClient";
import { AuthProvider, useAuth, type AuthUser } from "./useAuth";

vi.mock("@/shared/lib/apiClient", () => ({
  api: { get: vi.fn(), post: vi.fn() },
}));

beforeEach(() => vi.clearAllMocks());

const authUser: AuthUser = {
  id: "1",
  email: "a@b.co",
  displayName: "A",
  role: "admin",
  avatarUrl: null,
  isEphemeral: false,
};

function Consumer() {
  const { user, isLoading, signOut, setAuth, ensureSession } = useAuth();
  return (
    <div>
      <span>loading:{String(isLoading)}</span>
      <span>user:{user?.email ?? "none"}</span>
      <button onClick={() => setAuth(authUser)}>set</button>
      <button onClick={() => signOut()}>signout</button>
      <button onClick={() => ensureSession()}>ensure</button>
    </div>
  );
}

describe("AuthProvider", () => {
  it("restores the user by calling GET /api/v1/auth/me on mount", async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ user: authUser });
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("loading:false")).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith("/api/v1/auth/me");
    expect(screen.getByText("user:a@b.co")).toBeInTheDocument();
  });

  it("sets user to null when /auth/me fails", async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error("401"));
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("loading:false")).toBeInTheDocument());
    expect(screen.getByText("user:none")).toBeInTheDocument();
  });

  it("setAuth sets the user without a token argument", async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ user: null });
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("loading:false")).toBeInTheDocument());
    await act(async () => screen.getByText("set").click());
    expect(screen.getByText("user:a@b.co")).toBeInTheDocument();
  });

  it("signOut calls POST /api/v1/auth/logout and clears the user", async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ user: authUser });
    vi.mocked(api.post).mockResolvedValueOnce({ ok: true });
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("user:a@b.co")).toBeInTheDocument());
    await act(async () => screen.getByText("signout").click());
    expect(api.post).toHaveBeenCalledWith("/api/v1/auth/logout", {});
    expect(screen.getByText("user:none")).toBeInTheDocument();
  });

  it("ensureSession posts /auth/anon and sets the user when none is set", async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ user: null });
    vi.mocked(api.post).mockResolvedValueOnce({ user: authUser });
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("user:none")).toBeInTheDocument());
    await act(async () => screen.getByText("ensure").click());
    expect(api.post).toHaveBeenCalledWith("/api/v1/auth/anon", {});
    expect(screen.getByText("user:a@b.co")).toBeInTheDocument();
  });

  it("ensureSession is a no-op when a user is already set", async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ user: authUser });
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("user:a@b.co")).toBeInTheDocument());
    await act(async () => screen.getByText("ensure").click());
    expect(api.post).not.toHaveBeenCalled();
  });
});
