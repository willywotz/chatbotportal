import { AgencyLogo } from "@/shared/components/AgencyLogo";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import type { Agency } from "@/shared/types";

interface Props { agencies: Agency[] }

export function DashboardAgencyStatus({ agencies }: Props) {
  return (
    <Card className="animate-fade-in" style={{ animationDelay: "560ms", animationFillMode: "both" }}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">สถานะการเชื่อมต่อหน่วยงาน</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2.5">
          {agencies.map((a, i) => (
            <div
              key={a.id}
              className="flex items-center justify-between p-3 bg-muted/40 rounded-lg border border-border/50 hover:bg-muted/70 hover:border-border transition-all duration-200 animate-fade-in"
              style={{ animationDelay: `${600 + i * 60}ms`, animationFillMode: "both" }}
            >
              <div className="flex items-center gap-3">
                <div className="text-xl w-9 h-9 rounded-lg bg-card flex items-center justify-center shadow-sm border border-border/50">
                  <AgencyLogo logo={a.logo} alt={a.shortName} className="w-full h-full rounded-lg" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{a.shortName}</p>
                  <p className="text-[10px] text-muted-foreground">{a.connectionType} Protocol</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">{a.totalCalls?.toLocaleString()} calls</span>
                <span className={cn(
                  "text-[10px] font-medium px-2.5 py-1 rounded-full flex items-center gap-1",
                  a.status === 'active' ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'
                )}>
                  <span className={cn(
                    "w-1.5 h-1.5 rounded-full",
                    a.status === 'active' ? 'bg-success animate-pulse' : 'bg-destructive'
                  )} />
                  {a.status === 'active' ? 'Online' : 'Offline'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
