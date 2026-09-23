import { Line, LineChart, ResponsiveContainer } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import type { Agency } from "@/shared/types/agency";

import { HEALTH_LABEL } from "../lifecycle";
import { useHealthHistory } from "../useAgencies";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-normal text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xl font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}

export function OverviewTab({ agency }: { agency: Agency }) {
  const { data: history } = useHealthHistory(agency.id, "24h");
  const h = agency.health;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Uptime 24 ชม." value={h.uptime24h != null ? `${h.uptime24h}%` : "—"} />
        <Stat label="Latency เฉลี่ย" value={h.avgLatencyMs24h != null ? `${h.avgLatencyMs24h} ms` : "—"} />
        <Stat label="จำนวนครั้งที่เรียกใช้" value={agency.totalCalls.toLocaleString()} />
        <Stat label="คะแนน" value={`👍 ${agency.ratingUp} · 👎 ${agency.ratingDown}`} />
      </div>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">
            สุขภาพ 24 ชั่วโมง — {HEALTH_LABEL[h.state]}
          </CardTitle>
        </CardHeader>
        <CardContent className="h-24">
          {history && history.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={history}>
                <Line type="monotone" dataKey="avgLatencyMs" stroke="hsl(213 70% 45%)" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-muted-foreground">ยังไม่มีข้อมูล</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
