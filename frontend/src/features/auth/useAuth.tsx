import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { api } from "@/shared/lib/apiClient";
import { isAuthenticated, logout } from "@/shared/lib/oidc";
import { type Role } from "@/features/auth/roles";

export interface AuthUser {
  id: string;
  email: string;
  displayName: string;
  role: Role;
  avatarUrl: string | null;
}

interface AuthContextType {
  user: AuthUser | null;
  isAdmin: boolean;
  isLoading: boolean;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAdmin: false,
  isLoading: true,
  signOut: () => {},
});

export const useAuth = () => useContext(AuthContext);

/** The `/authentication/me` principal, as the FastAPI backend returns it (snake_case). */
interface MePayload {
  id: string;
  email: string;
  display_name?: string;
  role: Role;
}

function toAuthUser(payload: MePayload): AuthUser {
  return {
    id: payload.id,
    email: payload.email,
    displayName: payload.display_name ?? "",
    role: payload.role,
    avatarUrl: null,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount: the OIDC client (initialized in main.tsx) already knows whether a
  // session exists; if so, ask the backend who the bearer token belongs to.
  // Mock mode has no real OIDC provider (main.tsx skips initAuth()), so
  // `isAuthenticated()` stays false there — MSW's `/me` mock stands in for a
  // signed-in session instead.
  useEffect(() => {
    const mocks = import.meta.env.VITE_USE_MOCKS === "true";
    if (!isAuthenticated() && !mocks) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    api
      .get<MePayload>("/api/v1/authentication/me")
      .then((payload) => setUser(toAuthUser(payload)))
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  const signOut = useCallback(() => logout(), []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAdmin: user?.role === "admin",
        isLoading,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
