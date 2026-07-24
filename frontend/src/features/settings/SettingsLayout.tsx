import { Settings } from "lucide-react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/useAuth";
import { canAccess } from "@/features/auth/roles";
import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";

interface SettingsTab {
  label: string;
  path: string;
}

export const SETTINGS_TABS: SettingsTab[] = [
  { label: "ตั้งค่าระบบ", path: "/settings/system" },
  { label: "จัดการผู้ใช้", path: "/settings/users" },
  { label: "LLM", path: "/settings/llm" },
  { label: "API Keys", path: "/settings/api-keys" },
  { label: "การใช้งาน API Key", path: "/settings/usage" },
  { label: "ประวัติการเชื่อมต่อ", path: "/settings/connections" },
  { label: "บันทึกการตรวจสอบ", path: "/settings/audit" },
];

export function SettingsIndexRedirect() {
  const { user } = useAuth();
  if (user?.role === "admin") return <Navigate to="/settings/system" replace />;
  if (user?.role === "staff") return <Navigate to="/settings/usage" replace />;
  return <Navigate to="/chat" replace />;
}

export default function SettingsLayout() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const tabs = user ? SETTINGS_TABS.filter((t) => canAccess(user.role, t.path)) : [];
  const active = tabs.find((t) => t.path === location.pathname)?.path ?? tabs[0]?.path;

  return (
    <div>
      <div className="p-4 md:p-6 pb-0">
        <div className="mb-4 flex items-center gap-2">
          <Settings className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-semibold">ตั้งค่าระบบ</h1>
        </div>
        <Tabs value={active} onValueChange={(v) => navigate(v)}>
          <TabsList className="flex h-auto flex-wrap">
            {tabs.map((t) => (
              <TabsTrigger key={t.path} value={t.path}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      <Outlet />
    </div>
  );
}
