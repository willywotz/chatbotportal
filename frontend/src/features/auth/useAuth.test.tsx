import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Mocked react-oidc-context state the adapter reads.
const oidc: {
  isAuthenticated: boolean;
  isLoading: boolean;
  user?: { profile?: Record<string, unknown>; access_token?: string };
  signinRedirect: ReturnType<typeof vi.fn>;
  removeUser: ReturnType<typeof vi.fn>;
} = {
  isAuthenticated: false,
  isLoading: false,
  user: undefined,
  signinRedirect: vi.fn(),
  removeUser: vi.fn().mockResolvedValue(undefined),
};

vi.mock("react-oidc-context", () => ({ useAuth: () => oidc }));

import { useAuth } from "./useAuth";

beforeEach(() => {
  oidc.isAuthenticated = false;
  oidc.isLoading = false;
  oidc.user = undefined;
  oidc.signinRedirect = vi.fn();
  oidc.removeUser = vi.fn().mockResolvedValue(undefined);
});

describe("useAuth adapter", () => {
  it("maps the OIDC profile (id-token claims) to an AuthUser", () => {
    oidc.isAuthenticated = true;
    oidc.user = { profile: { sub: "1", email: "a@b.co", name: "A", role: "admin" } };
    const { result } = renderHook(() => useAuth());
    expect(result.current.user).toEqual({
      id: "1", email: "a@b.co", displayName: "A", role: "admin", avatarUrl: null,
    });
    expect(result.current.isAdmin).toBe(true);
    expect(result.current.isLoading).toBe(false);
  });

  it("returns a null user when not authenticated", () => {
    const { result } = renderHook(() => useAuth());
    expect(result.current.user).toBeNull();
    expect(result.current.isAdmin).toBe(false);
  });

  it("defaults role to 'user' when the claim is missing", () => {
    oidc.isAuthenticated = true;
    oidc.user = { profile: { sub: "2", email: "u@b.co" } };
    const { result } = renderHook(() => useAuth());
    expect(result.current.user?.role).toBe("user");
    expect(result.current.isAdmin).toBe(false);
  });

  it("signIn redirects with the returnTo state", () => {
    const { result } = renderHook(() => useAuth());
    result.current.signIn("/dashboard");
    expect(oidc.signinRedirect).toHaveBeenCalledWith({ state: { returnTo: "/dashboard" } });
  });

  it("signOut removes the local session", () => {
    const { result } = renderHook(() => useAuth());
    result.current.signOut();
    expect(oidc.removeUser).toHaveBeenCalled();
  });
});
