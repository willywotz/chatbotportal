import { Outlet, useLocation } from "react-router-dom";
import { SidebarProvider, SidebarTrigger } from "@/shared/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { User } from "lucide-react";
import { ThemeToggle } from "@/shared/components/ThemeToggle";
import { TextScaleControl } from "@/shared/components/TextScaleControl";

export function AppLayout() {
  const isChat = useLocation().pathname === "/chat";
  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <header className="h-14 border-b border-border bg-card flex items-center justify-between px-4 shrink-0">
            <div className="flex items-center gap-2">
              <SidebarTrigger />
              {/* <h1 className="text-base text-foreground hidden sm:block">
                Agentic AI Chatbot
              </h1> */}
            </div>
            <div className="flex items-center gap-3">
              {/* <span className="text-xs text-muted-foreground hidden sm:block">ระบบสนทนาอัจฉริยะกลางเพื่อเชื่อมโยงบริการภาครัฐ</span> */}
              {isChat && <TextScaleControl />}
              <ThemeToggle />
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                <User className="w-4 h-4 text-primary" />
              </div>
            </div>
          </header>
          {/* Main content */}
          <main className="flex-1 overflow-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
