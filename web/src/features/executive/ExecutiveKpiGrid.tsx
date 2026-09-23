import { Card, CardContent } from "@/shared/components/ui/card";
import { TrendingUp, TrendingDown, Users } from "lucide-react";

interface Kpis {
  thisMonthQuestions: number; lastMonthQuestions: number; momGrowthQuestions: number;
  thisYearQuestions: number; lastYearQuestions: number; yoyGrowthQuestions: number;
  thisMonthCitizens: number; lastMonthCitizens: number; momGrowthCitizens: number;
  thisYearCitizens: number; lastYearCitizens: number; yoyGrowthCitizens: number;
}

function StatCard({ label, value, sublabel, trend }: { label: string; value: string; sublabel?: string; trend?: number }) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground font-medium">{label}</p>
            <p className="text-2xl font-bold">{value}</p>
            {sublabel && <p className="text-xs text-muted-foreground">{sublabel}</p>}
          </div>
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Users className="h-5 w-5" />
          </div>
        </div>
        {trend !== undefined && (
          <div className="mt-3 flex items-center gap-1 text-xs">
            {trend >= 0 ? <TrendingUp className="h-3 w-3 text-success" /> : <TrendingDown className="h-3 w-3 text-destructive" />}
            <span className={trend >= 0 ? 'text-success font-semibold' : 'text-destructive font-semibold'}>
              {trend >= 0 ? '+' : ''}{trend}%
            </span>
            <span className="text-muted-foreground">เทียบกับเดือนก่อน</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface Props { kpis: Kpis }

export function ExecutiveKpiGrid({ kpis }: Props) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard label="คำถามรวมเดือนนี้" value={kpis.thisMonthQuestions.toLocaleString()} sublabel={`${kpis.lastMonthQuestions.toLocaleString()} คำถามในเดือนก่อน`} trend={kpis.momGrowthQuestions} />
      <StatCard label="คำถามรวมปีนี้" value={kpis.thisYearQuestions.toLocaleString()} sublabel={`${kpis.lastYearQuestions.toLocaleString()} คำถามในปีก่อน`} trend={kpis.yoyGrowthQuestions} />
      <StatCard label="ประชาชนที่ได้รับบริการเดือนนี้" value={kpis.thisMonthCitizens.toLocaleString()} sublabel={`${kpis.lastMonthCitizens.toLocaleString()} คนในเดือนก่อน`} trend={kpis.momGrowthCitizens} />
      <StatCard label="ประชาชนที่ได้รับบริการปีนี้" value={kpis.thisYearCitizens.toLocaleString()} sublabel={`${kpis.lastYearCitizens.toLocaleString()} คนในปีก่อน`} trend={kpis.yoyGrowthCitizens} />
    </div>
  );
}
