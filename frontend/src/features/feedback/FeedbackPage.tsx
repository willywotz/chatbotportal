import { useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
} from "recharts";
import { ThumbsDown } from "lucide-react";
import { useTheme } from "next-themes";

import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { PageHeader } from "@/shared/components/layout/PageHeader";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { QueryStateBoundary } from "@/shared/components/QueryStateBoundary";
import { useFeedbackStats } from "@/features/feedback/useFeedbackStats";
import { FeedbackSummaryCards } from "@/features/feedback/FeedbackSummaryCards";
import { ChartTooltip } from "@/shared/components/ChartTooltip";

export default function FeedbackPage() {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const { data: stats, isLoading, isError, refetch } = useFeedbackStats();

  const colors = useMemo(
    () => ({
      grid: isDark ? "hsl(220 15% 25%)" : "hsl(214 25% 92%)",
      tick: isDark ? "hsl(215 15% 60%)" : "hsl(215 15% 50%)",
      up: isDark ? "hsl(145 50% 50%)" : "hsl(145 55% 40%)",
      down: isDark ? "hsl(0 60% 55%)" : "hsl(0 65% 50%)",
    }),
    [isDark],
  );

  return (
    <div className="p-4 md:p-6 space-y-6">
      <PageHeader title="ความคิดเห็นและความพึงพอใจ" subtitle="วิเคราะห์ Feedback จากผู้ใช้งานระบบ" />

      <FeedbackSummaryCards />

      <QueryStateBoundary
        isLoading={isLoading}
        isError={isError}
        hasData={!!stats && stats.totalRatings > 0}
        onRetry={refetch}
        emptyMessage="ยังไม่มีข้อมูล Feedback"
        loading={<Skeleton className="h-72" />}
      >
        {/* empty state rendered by QueryStateBoundary when hasData=false */}
        {stats && stats.totalRatings > 0 && (
        <>
          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">
                  แนวโน้มความพึงพอใจรายวัน (14 วัน)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart
                    data={stats.dailyTrend}
                    margin={{ top: 5, right: 5, left: -15, bottom: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke={colors.grid}
                      vertical={false}
                    />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 10, fill: colors.tick }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: colors.tick }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line
                      type="monotone"
                      dataKey="up"
                      name="👍"
                      stroke={colors.up}
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="down"
                      name="👎"
                      stroke={colors.down}
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">
                  ความพึงพอใจแยกตามหน่วยงาน
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart
                    data={stats.agencyBreakdown}
                    layout="vertical"
                    margin={{ top: 0, right: 10, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke={colors.grid}
                      horizontal={false}
                    />
                    <XAxis
                      type="number"
                      tick={{ fontSize: 10, fill: colors.tick }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="agency"
                      width={100}
                      tick={{ fontSize: 10, fill: colors.tick }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="up" name="👍" stackId="a" fill={colors.up} radius={[0, 0, 0, 0]} />
                    <Bar
                      dataKey="down"
                      name="👎"
                      stackId="a"
                      fill={colors.down}
                      radius={[0, 4, 4, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          {stats.lowRatedQuestions.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">คำถามที่ได้คะแนนต่ำ (ล่าสุด)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {stats.lowRatedQuestions.map((q, i) => (
                    <div
                      key={`${q.created_at}-${q.content}`}
                      className="flex items-start gap-3 p-3 bg-destructive/5 border border-destructive/10 rounded-lg"
                    >
                      <ThumbsDown className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground line-clamp-2">{q.content}</p>
                        {q.feedback_text && (
                          <p className="text-xs text-muted-foreground mt-1 italic">
                            &ldquo;{q.feedback_text}&rdquo;
                          </p>
                        )}
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-[10px] bg-muted px-2 py-0.5 rounded-full">
                            {q.agency}
                          </span>
                          <span className="text-[10px] text-muted-foreground">
                            {new Date(q.created_at).toLocaleDateString("th-TH")}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
        )}
      </QueryStateBoundary>
    </div>
  );
}
