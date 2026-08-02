import { useState, useEffect, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area,
} from "recharts";
import { MessageSquare, TrendingUp, Clock, ThumbsUp, Loader2, Activity, ThumbsDown, AlertCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { useTheme } from "next-themes";

import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { useAgencies } from "@/features/agencies/useAgencies";
import { FeedbackSummaryCards } from "@/features/feedback/FeedbackSummaryCards";
import { useFeedbackStats } from "@/features/feedback/useFeedbackStats";
import { useDashboardStats, useAgencyUsage, useWeeklyTrend, useCategoryData, useLlmUsage } from "./useDashboard";
import { DashboardStatsRow } from "./DashboardStatsRow";
import { DashboardAgencyStatus } from "./DashboardAgencyStatus";
import { ChartTooltip } from "@/shared/components/ChartTooltip";

export default function DashboardPage() {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const { data: stats, isLoading: statsLoading, isError: statsError, dataUpdatedAt, refetch: refetchStats } = useDashboardStats();
  const { data: agencyUsage, isError: agencyUsageError } = useAgencyUsage();
  const { data: weeklyTrend, isError: weeklyTrendError } = useWeeklyTrend();
  const { data: categoryStats, isError: categoryError } = useCategoryData();
  const { data: agencies = [] } = useAgencies();
  const { data: feedbackStats } = useFeedbackStats();
  const { data: llmUsage = [] } = useLlmUsage("model");

  const anyError = statsError || agencyUsageError || weeklyTrendError || categoryError;

  const chartColors = useMemo(() => ({
    grid: isDark ? "hsl(220 15% 25%)" : "hsl(214 25% 92%)",
    tick: isDark ? "hsl(215 15% 60%)" : "hsl(215 15% 50%)",
    primary: isDark ? "hsl(213 65% 60%)" : "hsl(213 70% 45%)",
    dotStroke: isDark ? "hsl(220 18% 14%)" : "white",
    palette: isDark
      ? ["hsl(145 50% 50%)", "hsl(213 65% 60%)", "hsl(25 80% 60%)", "hsl(280 45% 60%)"]
      : ["hsl(145 55% 40%)", "hsl(213 70% 45%)", "hsl(25 85% 55%)", "hsl(280 50% 50%)"],
  }), [isDark]);

  const [lastUpdated, setLastUpdated] = useState("");
  useEffect(() => {
    if (dataUpdatedAt) {
      setLastUpdated(new Date(dataUpdatedAt).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    }
  }, [dataUpdatedAt]);

  const totalUsage = agencyUsage?.reduce((sum, a) => sum + a.value, 0) || 1;

  const statCards = useMemo(() => stats ? [
    { label: "คำถามทั้งหมด", value: stats.totalQuestions.toLocaleString(), icon: MessageSquare, color: "text-primary" },
    { label: "คำถามวันนี้", value: stats.todayQuestions.toLocaleString(), icon: TrendingUp, color: "text-success" },
    { label: "เวลาตอบเฉลี่ย", value: `${stats.avgResponseTime}s`, icon: Clock, color: "text-warning" },
    { label: "ความพึงพอใจ", value: `${stats.satisfactionRate}%`, icon: ThumbsUp, color: "text-info" },
  ] : [], [stats]);

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {anyError && (
        <div role="alert" aria-live="assertive" className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>เกิดข้อผิดพลาดในการโหลดข้อมูล</span>
          <button onClick={() => refetchStats()} className="ml-auto underline text-xs">ลองอีกครั้ง</button>
        </div>
      )}
      <div className="flex items-center justify-between animate-fade-in">
        <div>
          <h2 className="text-lg text-foreground">Dashboard สถิติการใช้งาน</h2>
          <p className="text-xs text-muted-foreground mt-0.5">ภาพรวมการใช้งานระบบ AI ประสานงานภาครัฐ</p>
        </div>
        {lastUpdated && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground bg-muted/50 px-3 py-1.5 rounded-full">
            <Activity className="h-3 w-3 text-success animate-pulse" />
            <span>Live</span>
            <span className="text-muted-foreground/60">•</span>
            <span>{lastUpdated}</span>
          </div>
        )}
      </div>

      <DashboardStatsRow statCards={statCards} />

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="animate-fade-in" style={{ animationDelay: "320ms", animationFillMode: "both" }}>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">แนวโน้มการใช้งานรายสัปดาห์</CardTitle>
              <span className="text-[10px] text-muted-foreground bg-muted px-2 py-1 rounded-full">7 วันล่าสุด</span>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={weeklyTrend} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradientQuestions" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={chartColors.primary} stopOpacity={isDark ? 0.25 : 0.3} />
                    <stop offset="95%" stopColor={chartColors.primary} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: chartColors.tick }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: chartColors.tick }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="questions" name="คำถาม" stroke={chartColors.primary}
                  strokeWidth={2.5} fill="url(#gradientQuestions)"
                  dot={{ r: 4, fill: chartColors.primary, stroke: chartColors.dotStroke, strokeWidth: 2 }}
                  activeDot={{ r: 6, fill: chartColors.primary, stroke: chartColors.dotStroke, strokeWidth: 2 }}
                  animationDuration={1200} animationEasing="ease-out"
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="animate-fade-in" style={{ animationDelay: "400ms", animationFillMode: "both" }}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">สัดส่วนการเรียกใช้หน่วยงาน</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <ResponsiveContainer width="55%" height={220}>
                <PieChart>
                  <Pie data={agencyUsage} dataKey="value" nameKey="name" cx="50%" cy="50%"
                    outerRadius={85} innerRadius={55} paddingAngle={3} cornerRadius={4}
                    animationDuration={1000} animationEasing="ease-out"
                  >
                    {agencyUsage?.map((_, i) => (
                      <Cell key={i} fill={chartColors.palette[i % chartColors.palette.length]} stroke="none" />
                    ))}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2.5">
                {agencyUsage?.map((entry, i) => (
                  <div key={i} className="group">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: chartColors.palette[i % chartColors.palette.length] }} />
                        <span className="text-foreground font-medium">{entry.name}</span>
                      </div>
                      <span className="text-muted-foreground">{((entry.value / totalUsage) * 100).toFixed(0)}%</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden ml-[18px]">
                      <div className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${(entry.value / totalUsage) * 100}%`, backgroundColor: chartColors.palette[i % chartColors.palette.length] }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="animate-fade-in" style={{ animationDelay: "480ms", animationFillMode: "both" }}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">หมวดหมู่คำถามยอดนิยม</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={categoryStats} layout="vertical" margin={{ top: 0, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10, fill: chartColors.tick }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="category" width={110} tick={{ fontSize: 11, fill: chartColors.tick }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" name="จำนวน" radius={[0, 6, 6, 0]} animationDuration={1000} animationEasing="ease-out">
                  {categoryStats?.map((_, i) => (
                    <Cell key={i} fill={chartColors.palette[i % chartColors.palette.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <DashboardAgencyStatus agencies={agencies} />
      </div>

      <Card className="animate-fade-in" style={{ animationDelay: "560ms", animationFillMode: "both" }}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">LLM cost (by model)</CardTitle>
        </CardHeader>
        <CardContent>
          {llmUsage.length === 0 ? (
            <p className="text-xs text-muted-foreground">No data</p>
          ) : (
            <>
              <p className="text-2xl font-semibold text-foreground mb-3">
                ${llmUsage.reduce((sum, r) => sum + r.cost_usd, 0).toFixed(4)}
              </p>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted-foreground">
                    <th className="text-left pb-1">Model</th>
                    <th className="text-right pb-1">Cost (USD)</th>
                    <th className="text-right pb-1">Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {llmUsage.map((row) => (
                    <tr key={row.key} className="border-t border-border/50">
                      <td className="py-1 text-foreground">{row.key}</td>
                      <td className="py-1 text-right text-muted-foreground">${row.cost_usd.toFixed(4)}</td>
                      <td className="py-1 text-right text-muted-foreground">{(row.prompt_tokens + row.completion_tokens).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base text-foreground">📊 Feedback</h3>
          <Link to="/feedback" className="text-xs text-primary hover:underline">ดูทั้งหมด →</Link>
        </div>
        <FeedbackSummaryCards />
        {feedbackStats && feedbackStats.lowRatedQuestions.length > 0 && (
          <div className="space-y-2">
            {feedbackStats.lowRatedQuestions.slice(0, 3).map((q, i) => (
              <div key={`${q.created_at}-${q.content}`} className="flex items-start gap-3 p-3 bg-destructive/5 border border-destructive/10 rounded-lg">
                <ThumbsDown className="h-3.5 w-3.5 text-destructive shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-foreground line-clamp-1">{q.content}</p>
                  {q.feedback_text && (
                    <p className="text-xs text-muted-foreground mt-1 italic">
                      &ldquo;{q.feedback_text}&rdquo;
                    </p>
                  )}
                  <span className="text-[10px] bg-muted px-2 py-0.5 rounded-full mt-1 inline-block">{q.agency}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
