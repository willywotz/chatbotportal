import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { completeLogin } from "@/shared/lib/oidc";
import { Skeleton } from "@/shared/components/ui/skeleton";

export default function CallbackPage() {
  const navigate = useNavigate();
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;
    completeLogin()
      .then((user) => {
        const returnTo = (user.state as { returnTo?: string } | undefined)?.returnTo;
        navigate(returnTo || "/chat", { replace: true });
      })
      .catch(() => navigate("/login", { replace: true }));
  }, [navigate]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="space-y-4 w-64">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    </div>
  );
}
