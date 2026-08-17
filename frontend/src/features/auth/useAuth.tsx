import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { api } from "@/shared/lib/apiClient";
import { type Role } from "@/features/auth/roles";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: string;
  email: string;
  displayName: string;
  role: Role;
  avatarUrl: string | null;
  isEphemeral: boolean;
}

interface AuthContextType {
  user: AuthUser | null;
  isAdmin: boolean;
  isLoading: boolean;
  signOut: () => void;
  /** Call after a successful login to set the authenticated user */
  setAuth: (user: AuthUser) => void;
  /** Bootstraps an anonymous session when no user is signed in; no-op otherwise */
  ensureSession: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAdmin: false,
  isLoading: true,
  signOut: () => {},
  setAuth: () => {},
  ensureSession: async () => {},
});

export const useAuth = () => useContext(AuthContext);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount: the session cookie (if any) is sent automatically — ask the
  // server who we are.
  useEffect(() => {
    api
      .get<{ user: AuthUser }>("/api/v1/auth/me")
      .then(({ user }) => setUser(user))
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  const setAuth = useCallback((authUser: AuthUser) => setUser(authUser), []);

  const signOut = useCallback(() => {
    api.post("/api/v1/auth/logout", {}).catch(() => {});
    setUser(null);
  }, []);

  const ensureSession = useCallback(async () => {
    if (user) return;
    try {
      const res = await api.post<{ user: AuthUser }>("/api/v1/auth/anonymous", {});
      setUser(res.user);
    } catch {
      // Proceed anyway; the chat request may 401 and surface an error.
    }
  }, [user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAdmin: user?.role === "admin",
        isLoading,
        signOut,
        setAuth,
        ensureSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
