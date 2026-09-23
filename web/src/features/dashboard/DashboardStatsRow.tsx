import { memo } from "react";
import { Card, CardContent } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import type { LucideIcon } from "lucide-react";

interface StatCard {
  label: string;
  value: string;
  icon: LucideIcon;
  color: string;
}

interface Props {
  statCards: StatCard[];
}

export const DashboardStatsRow = memo(function DashboardStatsRow({ statCards }: Props) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {statCards.map((s, i) => (
        <Card
          key={i}
          className={cn(
            "group relative overflow-hidden transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 animate-fade-in",
          )}
          style={{ animationDelay: `${i * 80}ms`, animationFillMode: "both" }}
        >
          <CardContent className="p-4 relative z-10">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-muted-foreground font-medium">{s.label}</span>
              <div className={cn("p-2 rounded-lg bg-muted/80 transition-colors group-hover:bg-primary/10", s.color)}>
                <s.icon className="h-4 w-4" />
              </div>
            </div>
            <p className="text-2xl font-bold text-foreground tracking-tight">{s.value}</p>
          </CardContent>
          <div className="absolute inset-0 bg-gradient-to-br from-primary/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
        </Card>
      ))}
    </div>
  );
});
