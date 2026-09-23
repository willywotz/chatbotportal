import { useCallback, useEffect } from "react";
import { useAuth as useOidcAuth } from "react-oidc-context";

import { beginLogout, setAccessToken, setOnUnauthenticated } from "@/shared/lib/authToken";
import { type Role } from "@/features/auth/roles";

export interface AuthUser {
  id: string;
  email: string;
  displayName: string;
  role: Role;
  avatarUrl: string | null;
}

export interface AuthState {
  user: AuthUser | null;
  isAdmin: boolean;
  isLoading: boolean;
  signIn: (returnTo?: string) => void;
  signOut: () => void;
}

/**
 * App-facing auth hook. Wraps react-oidc-context and derives the user straight
 * from the OIDC profile (id-token claims) — no `/authentication/me` call.
 */
export function useAuth(): AuthState {
  // `oidc` is undefined only outside an <AuthProvider> (isolated component tests
  // that render a consumer directly); the real app always has the provider.
  const oidc = useOidcAuth() as ReturnType<typeof useOidcAuth> | undefined;

  const signIn = useCallback(
    (returnTo?: string) => {
      void oidc?.signinRedirect({
        state: { returnTo: returnTo ?? window.location.pathname + window.location.search },
      });
    },
    [oidc],
  );

  const signOut = useCallback(() => {
    // No RP-initiated logout endpoint on the provider; drop the local session
    // and hard-navigate home. beginLogout() suppresses ProtectedRoute's
    // auto-redirect so removeUser flipping to unauthenticated does not bounce us
    // to the login page before "/" loads.
    beginLogout();
    void oidc?.removeUser();
    window.location.href = "/";
  }, [oidc]);

  const profile = oidc?.user?.profile;
  const user: AuthUser | null =
    oidc?.isAuthenticated && profile
      ? {
          id: String(profile.sub ?? ""),
          email: (profile.email as string) ?? "",
          displayName: (profile.name as string) || (profile.email as string) || "",
          role: (profile.role as Role) ?? "user",
          avatarUrl: null,
        }
      : null;

  return {
    user,
    isAdmin: user?.role === "admin",
    isLoading: oidc?.isLoading ?? false,
    signIn,
    signOut,
  };
}

/**
 * Bridges the OIDC access token (React state) into the non-React axios client.
 * Mounted once inside the provider; keeps `authToken` current and wires 401
 * re-login. Renders nothing.
 */
export function AuthTokenSync(): null {
  const oidc = useOidcAuth() as ReturnType<typeof useOidcAuth> | undefined;
  const token = oidc?.user?.access_token;

  useEffect(() => {
    setAccessToken(token);
  }, [token]);

  useEffect(() => {
    setOnUnauthenticated(() => {
      void oidc?.signinRedirect();
    });
    return () => setOnUnauthenticated(undefined);
  }, [oidc]);

  return null;
}
