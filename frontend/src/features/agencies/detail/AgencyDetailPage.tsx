import { ArrowLeft, ArrowRight, ChevronDown } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { AgencyLogo } from "@/shared/components/AgencyLogo";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import type { AgencyLifecycleStatus } from "@/shared/types/agency";

import {
  HEALTH_DOT_CLASS,
  legalTransitions,
  STATUS_BADGE_CLASS,
  STATUS_LABEL,
  TRANSITION_LABEL,
} from "../lifecycle";
import { useAgencies, useUpdateAgencyStatus } from "../useAgencies";
import { EditTab } from "./EditTab";
import { HealthTab } from "./HealthTab";
import { LogsTab } from "./LogsTab";
import { OverviewTab } from "./OverviewTab";

export default function AgencyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data: agencies = [], isLoading } = useAgencies();
  const statusMutation = useUpdateAgencyStatus();

  const agency = agencies.find((a) => a.id === id);

  if (isLoading) {
    return (
      <div className="p-4 md:p-6 space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!agency) {
    return (
      <div className="p-4 md:p-6 text-center space-y-4">
        <p className="text-muted-foreground">ไม่พบหน่วยงาน</p>
        <Button variant="outline" onClick={() => navigate("/agencies")}>
          <ArrowLeft className="h-4 w-4 mr-2" /> กลับ
        </Button>
      </div>
    );
  }

  const changeStatus = async (status: AgencyLifecycleStatus) => {
    try {
      await statusMutation.mutateAsync({ id: agency.id, status });
      toast.success(`เปลี่ยนสถานะเป็น ${STATUS_LABEL[status]} สำเร็จ`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    }
  };

  const showHealthDot = agency.status === "active" || agency.status === "maintenance";
  const requestedTab = searchParams.get("tab");
  const defaultTab = requestedTab === "edit" ? "edit" : "overview";

  return (
    <div className="p-4 md:p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate("/agencies")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl"
            style={{ backgroundColor: `${agency.color}15` }}
          >
            <AgencyLogo logo={agency.logo} alt={agency.name} className="w-full h-full rounded-xl" />
          </div>
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              {agency.name}
              {showHealthDot && (
                <span className={`inline-block w-2.5 h-2.5 rounded-full ${HEALTH_DOT_CLASS[agency.health.state]}`} />
              )}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <Badge className={`text-[10px] ${STATUS_BADGE_CLASS[agency.status]}`}>
                {STATUS_LABEL[agency.status]}
              </Badge>
              <Badge variant="outline" className="text-[10px]">{agency.connectionType}</Badge>
            </div>
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              สถานะ <ChevronDown className="h-3.5 w-3.5 ml-1" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {legalTransitions(agency.status)
              // Draft → active requires the conformance battery, run only by the setup wizard.
              .filter((to) => !(agency.status === "draft" && to === "active"))
              .map((to) => (
                <DropdownMenuItem key={to} onClick={() => changeStatus(to)}>
                  {TRANSITION_LABEL[to]}
                </DropdownMenuItem>
              ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {agency.status === "draft" && (
        <div className="rounded-lg border border-dashed border-border p-4 flex items-center justify-between">
          <p className="text-sm text-muted-foreground">หน่วยงานนี้ยังตั้งค่าไม่เสร็จ</p>
          <Link
            to={`/agencies/${agency.id}/setup`}
            className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
          >
            ตั้งค่าต่อ <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}

      <Tabs defaultValue={defaultTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">ภาพรวม</TabsTrigger>
          <TabsTrigger value="health">Health</TabsTrigger>
          <TabsTrigger value="edit">แก้ไข</TabsTrigger>
          <TabsTrigger value="logs">Logs</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <OverviewTab agency={agency} />
        </TabsContent>
        <TabsContent value="health">
          <HealthTab agencyId={agency.id} />
        </TabsContent>
        <TabsContent value="edit">
          <EditTab agency={agency} />
        </TabsContent>
        <TabsContent value="logs">
          <LogsTab agencyId={agency.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
