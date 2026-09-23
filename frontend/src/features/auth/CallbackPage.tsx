import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth as useOidcAuth } from "react-oidc-context";
import { Skeleton } from "@/shared/components/ui/skeleton";

/**
 * OIDC redirect landing. react-oidc-context processes the Authorization Code +
 * PKCE response automatically; this page waits for that to settle, then routes
 * to the pre-login location (carried in the OIDC `state`) or /chat.
 */
export default function CallbackPage() {
  const auth = useOidcAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (auth.isLoading || auth.activeNavigator) return;
    if (auth.isAuthenticated) {
      const returnTo = (auth.user?.state as { returnTo?: string } | undefined)?.returnTo;
      navigate(returnTo || "/chat", { replace: true });
    } else if (auth.error) {
      navigate("/login", { replace: true });
    }
  }, [auth.isLoading, auth.activeNavigator, auth.isAuthenticated, auth.error, auth.user, navigate]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="space-y-4 w-64">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    </div>
  );
}
