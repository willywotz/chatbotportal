import { useExecutiveSummary, useRegenerateExecutiveSummary } from "./useExecutive";
import { useAuth } from "@/features/auth/useAuth";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { ExecutiveKpiGrid } from "./ExecutiveKpiGrid";
import { ExecutiveTrendChart } from "./ExecutiveTrendChart";
import { ExecutiveWeeklyBrief } from "./ExecutiveWeeklyBrief";

export default function ExecutivePage() {
  const { data, isLoading, error, refetch } = useExecutiveSummary();
  const { isAdmin } = useAuth();
  const regenerate = useRegenerateExecutiveSummary();

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-12 w-96" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-32" />)}
        </div>
        <Skeleton className="h-80" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <Card className="border-destructive/50">
          <CardContent className="p-8 text-center space-y-3">
            <AlertCircle className="h-10 w-10 mx-auto text-destructive" />
            <p className="font-semibold">ไม่สามารถโหลดข้อมูลผู้บริหารได้</p>
            <Button onClick={() => refetch()} variant="outline">ลองอีกครั้ง</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { kpis, monthlyTrend, weeklyBrief, generatedAt } = data;

  return (
    <div className="p-6 space-y-6 mx-auto">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl tracking-tight portal-gradient-text">Executive Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">
            ภาพรวมเชิงกลยุทธ์สำหรับผู้บริหาร · อัปเดตล่าสุด {new Date(generatedAt).toLocaleString('th-TH')}
          </p>
        </div>
      </div>
      <ExecutiveKpiGrid kpis={kpis} />
      <ExecutiveTrendChart monthlyTrend={monthlyTrend} />
      <ExecutiveWeeklyBrief
        weeklyBrief={weeklyBrief}
        canRegenerate={isAdmin}
        isRegenerating={regenerate.isPending}
        onRegenerate={() => regenerate.mutate()}
      />
    </div>
  );
}
