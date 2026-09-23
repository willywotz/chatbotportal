import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip } from "recharts";
import { Activity, Zap } from "lucide-react";
import { useRealtimeActivity, type RealtimeEvent } from "@/features/dashboard/useRealtimeActivity";
import { Badge } from "@/shared/components/ui/badge";
import { cn } from "@/shared/lib/utils";
import { useTheme } from "next-themes";
import { useMemo } from "react";
import { ChartTooltip } from "@/shared/components/ChartTooltip";

function LiveEventItem({ event }: { event: RealtimeEvent }) {
  return (
    <div className="flex items-center gap-2 py-1.5 px-2 rounded-md bg-muted/40 animate-fade-in">
      <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse shrink-0" />
      <span className="text-xs text-foreground truncate flex-1">{event.title}</span>
      <div className="flex gap-1 shrink-0">
        {event.agencies.slice(0, 2).map((a, i) => (
          <Badge key={i} variant="outline" className="text-[9px] px-1.5 py-0">{a}</Badge>
        ))}
      </div>
      <span className="text-[9px] text-muted-foreground shrink-0">
        {event.timestamp.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </span>
    </div>
  );
}

export function LiveActivityChart() {
  const { events, buckets, totalLive } = useRealtimeActivity();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const colors = useMemo(() => ({
    stroke: isDark ? "hsl(152 55% 50%)" : "hsl(152 55% 42%)",
    grid: isDark ? "hsl(220 15% 25%)" : "hsl(214 25% 92%)",
    tick: isDark ? "hsl(215 15% 60%)" : "hsl(215 15% 50%)",
    dotStroke: isDark ? "hsl(220 18% 14%)" : "white",
  }), [isDark]);

  const hasActivity = buckets.some(b => b.count > 0);

  return (
    <Card className="animate-fade-in" style={{ animationDelay: "200ms", animationFillMode: "both" }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm font-medium">Live Activity</CardTitle>
            <div className="flex items-center gap-1 text-[10px] text-success bg-success/10 px-2 py-0.5 rounded-full">
              <Activity className="h-3 w-3 animate-pulse" />
              Realtime
            </div>
          </div>
          {totalLive > 0 && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Zap className="h-3 w-3 text-warning" />
              <span>{totalLive} คำถามล่าสุด</span>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid lg:grid-cols-5 gap-4">
          {/* Chart */}
          <div className="lg:col-span-3">
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={buckets} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradientLive" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={colors.stroke} stopOpacity={isDark ? 0.3 : 0.35} />
                    <stop offset="95%" stopColor={colors.stroke} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 9, fill: colors.tick }}
                  axisLine={false}
                  tickLine={false}
                  interval={Math.floor(buckets.length / 5)}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 9, fill: colors.tick }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<ChartTooltip valueSuffix=" คำถาม" />} />
                <Area
                  type="monotone"
                  dataKey="count"
                  name="คำถาม"
                  stroke={colors.stroke}
                  strokeWidth={2}
                  fill="url(#gradientLive)"
                  dot={false}
                  activeDot={{ r: 4, fill: colors.stroke, stroke: colors.dotStroke, strokeWidth: 2 }}
                  animationDuration={300}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
            {!hasActivity && (
              <p className="text-center text-[10px] text-muted-foreground -mt-4">
                รอคำถามใหม่... กราฟจะอัปเดตอัตโนมัติแบบ realtime
              </p>
            )}
          </div>

          {/* Recent events feed */}
          <div className="lg:col-span-2 space-y-1.5 max-h-[180px] overflow-y-auto">
            {events.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center py-6">
                <Activity className="h-6 w-6 text-muted-foreground/40 mb-2" />
                <p className="text-xs text-muted-foreground">ยังไม่มีคำถามใหม่</p>
                <p className="text-[10px] text-muted-foreground/60 mt-0.5">จะแสดงเมื่อมีคำถามเข้ามา</p>
              </div>
            ) : (
              events.slice(0, 8).map((e) => (
                <LiveEventItem key={e.id} event={e} />
              ))
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
