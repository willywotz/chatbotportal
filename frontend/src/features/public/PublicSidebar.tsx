import { MessageSquare } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/shared/components/ui/sidebar";
import type { PublicAgency } from "@/features/public/publicAgenciesApi";

interface PublicSidebarProps {
  agencies: PublicAgency[];
  onNewChat: () => void;
}

/** Public-portal sidebar mirroring AppSidebar, limited to the chat nav and connected agencies. */
export function PublicSidebar({ agencies, onNewChat }: PublicSidebarProps) {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarContent>
        {!collapsed && (
          <div className="p-4 border-b border-sidebar-border">
            <p className="font-semibold text-sm text-sidebar-foreground">Agentic AI Chatbot</p>
            <p className="text-[10px] text-muted-foreground">ระบบบูรณาการข้อมูล</p>
          </div>
        )}

        <SidebarGroup>
          {/* <SidebarGroupLabel>เมนูหลัก</SidebarGroupLabel> */}
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton tooltip="แชทใหม่" onClick={onNewChat}>
                  <MessageSquare className="h-4 w-4 shrink-0" />
                  <span>แชทใหม่</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {!collapsed && agencies.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel>หน่วยงานที่เชื่อมต่อ</SidebarGroupLabel>
            <SidebarGroupContent>
              <div className="px-3 space-y-2">
                {agencies.map((agency) => (
                  <div key={agency.id} className="flex items-center gap-2 text-xs">
                    <span className="w-2 h-2 rounded-full bg-green-500 shrink-0" />
                    <span className="text-sidebar-foreground truncate">{agency.shortName}</span>
                  </div>
                ))}
              </div>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
    </Sidebar>
  );
}
