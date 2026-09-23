import { memo } from "react";
import { ArrowRight, MoreVertical, Pencil, Trash2, Wifi } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { AgencyLogo } from "@/shared/components/AgencyLogo";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import type { Agency, AgencyLifecycleStatus } from "@/shared/types/agency";

import { ConnectionTestResult, type TestResult } from "./ConnectionTestResult";
import {
  HEALTH_DOT_CLASS,
  legalTransitions,
  STATUS_BADGE_CLASS,
  STATUS_LABEL,
  TRANSITION_LABEL,
} from "./lifecycle";

const connectionTypeColors: Record<string, string> = {
  MCP: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  API: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  A2A: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

interface Props {
  agency: Agency;
  onTest: (agency: Agency) => void;
  onDelete?: (agency: Agency) => void;
  onStatusChange?: (agency: Agency, status: AgencyLifecycleStatus) => void;
  testing: boolean;
  testResult: TestResult | null;
  manageActions?: boolean;
}

export const AgencyCard = memo(function AgencyCard({
  agency,
  onTest,
  onDelete,
  onStatusChange,
  testing,
  testResult,
  manageActions = true,
}: Props) {
  const navigate = useNavigate();
  const showHealth = agency.status === "active" || agency.status === "maintenance";
  const uptime = agency.health.uptime24h;

  return (
    <Card
      className={`overflow-hidden cursor-pointer hover:shadow-md transition-shadow ${
        agency.status === "disabled" ? "opacity-60" : ""
      } ${agency.status === "draft" ? "border-dashed" : ""} ${
        agency.status === "maintenance" ? "border-amber-300 dark:border-amber-700" : ""
      }`}
      onClick={() => navigate(`/agencies/${agency.id}`)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl"
              style={{ backgroundColor: `${agency.color}15` }}
            >
              <AgencyLogo logo={agency.logo} alt={agency.name} className="w-full h-full rounded-xl" />
            </div>
            <div>
              <CardTitle className="text-sm flex items-center gap-1.5">
                {agency.name}
                {showHealth && (
                  <span className={`inline-block w-2 h-2 rounded-full ${HEALTH_DOT_CLASS[agency.health.state]}`} />
                )}
              </CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">{agency.description}</p>
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="actions" onClick={(e) => e.stopPropagation()}>
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); navigate(`/agencies/${agency.id}?tab=edit`); }}>
                <Pencil className="h-3.5 w-3.5 mr-2" /> แก้ไข
              </DropdownMenuItem>
              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onTest(agency); }}>
                <Wifi className="h-3.5 w-3.5 mr-2" /> ทดสอบการเชื่อมต่อ
              </DropdownMenuItem>
              {manageActions && (
                <>
                  <DropdownMenuSeparator />
                  {legalTransitions(agency.status).map((to) => (
                    <DropdownMenuItem
                      key={to}
                      onClick={(e) => { e.stopPropagation(); onStatusChange?.(agency, to); }}
                    >
                      {TRANSITION_LABEL[to]}
                    </DropdownMenuItem>
                  ))}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={(e) => { e.stopPropagation(); onDelete?.(agency); }}
                    className="text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-2" /> ลบ
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Badge className={`text-[10px] ${connectionTypeColors[agency.connectionType] || ""}`}>
            {agency.connectionType}
          </Badge>
          <Badge className={`text-[10px] ${STATUS_BADGE_CLASS[agency.status]}`}>
            {STATUS_LABEL[agency.status]}
          </Badge>
          {agency.priority != null && (
            <Badge variant="outline" className="text-[10px]">P{agency.priority}</Badge>
          )}
        </div>

        {showHealth && (
          <div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  agency.health.state === "up"
                    ? "bg-green-500"
                    : agency.health.state === "degraded"
                      ? "bg-amber-500"
                      : "bg-red-500"
                }`}
                style={{ width: `${uptime ?? 0}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
              <span>uptime 24h · {uptime != null ? `${uptime}%` : "—"}</span>
              <span>
                {agency.health.avgLatencyMs24h != null ? `${agency.health.avgLatencyMs24h} ms` : "—"}
              </span>
            </div>
          </div>
        )}

        {agency.status === "draft" && (
          <Link
            to={`/agencies/${agency.id}/setup`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            ตั้งค่าต่อ <ArrowRight className="h-3 w-3" />
          </Link>
        )}

        <div className="flex items-center justify-between pt-2 border-t border-border">
          <span className="text-xs text-muted-foreground">จำนวนครั้งที่เรียกใช้</span>
          <span className="text-sm font-semibold text-foreground">{agency.totalCalls.toLocaleString()}</span>
        </div>

        {(testing || testResult) && <ConnectionTestResult result={testResult} loading={testing} />}
      </CardContent>
    </Card>
  );
});
