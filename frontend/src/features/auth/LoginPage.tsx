import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { login } from "@/shared/lib/oidc";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { ArrowLeft, LogIn } from "lucide-react";

export default function LoginPage() {
  const navigate = useNavigate();
  const { user, isLoading } = useAuth();

  // Redirect if already logged in
  useEffect(() => {
    if (!isLoading && user) {
      navigate("/chat", { replace: true });
    }
  }, [user, isLoading, navigate]);

  if (!isLoading && user) return null;

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center space-y-2">
          <CardTitle className="text-xl">เข้าสู่ระบบ Admin</CardTitle>
          <p className="text-sm text-muted-foreground">
            Agentic AI Chatbot — ระบบบูรณาการข้อมูลหน่วยงานภาครัฐ
          </p>
        </CardHeader>
        <CardContent>
          <Button className="w-full" onClick={() => login()}>
            <LogIn className="h-4 w-4 mr-2" />
            เข้าสู่ระบบ
          </Button>
          <Link
            to="/"
            className="mt-4 flex items-center justify-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            กลับสู่หน้าหลัก
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
