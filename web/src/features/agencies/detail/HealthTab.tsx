import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import type { HealthWindow } from "@/shared/types/agency";

import { useHealthHistory } from "../useAgencies";

const WINDOWS: HealthWindow[] = ["24h", "7d", "30d"];

export function HealthTab({ agencyId }: { agencyId: string }) {
  // "win" not "window" — avoid shadowing the global.
  const [win, setWin] = useState<HealthWindow>("24h");
  const { data, isLoading, isError, refetch } = useHealthHistory(agencyId, win);

  const chartData = (data ?? []).map((b) => ({
    ...b,
    time: new Date(b.bucketStart).toLocaleString("th-TH", {
      day: win === "24h" ? undefined : "numeric",
      month: win === "24h" ? undefined : "short",
      hour: win === "30d" ? undefined : "2-digit",
      minute: win === "30d" ? undefined : "2-digit",
    }),
  }));

  if (isError) {
    return (
      <div className="rounded-lg border border-border p-8 text-center space-y-3">
        <p className="text-sm text-muted-foreground">โหลดข้อมูลไม่สำเร็จ</p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          ลองใหม่
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {WINDOWS.map((w) => (
          <Button
            key={w}
            size="sm"
            variant={win === w ? "default" : "outline"}
            aria-pressed={win === w}
            onClick={() => setWin(w)}
          >
            {w}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Uptime (%)</CardTitle>
        </CardHeader>
        <CardContent className="h-48">
          {isLoading ? (
            <p className="text-xs text-muted-foreground">กำลังโหลด…</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="time" tick={{ fontSize: 10 }} minTickGap={32} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} width={32} />
                <Tooltip />
                <Area
                  type="monotone"
                  dataKey="uptimePct"
                  name="uptime %"
                  stroke="hsl(152 55% 42%)"
                  fill="hsl(152 55% 42% / 0.15)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Latency (ms)</CardTitle>
        </CardHeader>
        <CardContent className="h-48">
          {isLoading ? (
            <p className="text-xs text-muted-foreground">กำลังโหลด…</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="time" tick={{ fontSize: 10 }} minTickGap={32} />
                <YAxis tick={{ fontSize: 10 }} width={40} />
                <Tooltip />
                <Line type="monotone" dataKey="avgLatencyMs" name="latency ms" stroke="hsl(213 70% 45%)" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
