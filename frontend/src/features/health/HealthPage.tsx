import { useAgencyHealth } from './useHealth';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/components/ui/card';
import { Badge } from '@/shared/components/ui/badge';
import { QueryStateBoundary } from '@/shared/components/QueryStateBoundary';
import { Activity, AlertCircle, CheckCircle2, XCircle, Zap } from 'lucide-react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { AgencyHealthData } from './healthApi';
import { HEALTH_STATUS_LABEL as STATUS_LABELS, HEALTH_STATUS_COLOR as STATUS_COLORS } from '@/shared/constants/status';

const AGENCY_COLORS = ['hsl(213 70% 50%)', 'hsl(280 60% 55%)', 'hsl(35 90% 55%)', 'hsl(160 60% 45%)'];

function HealthContent({ data }: { data: AgencyHealthData }) {
  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl flex items-center gap-2">
            <Activity className="h-7 w-7 text-primary" />
            Agency Health Monitoring
          </h1>
          <p className="text-muted-foreground mt-1">Real-time uptime, latency และ historical chart</p>
        </div>
        <Badge variant="outline" className="text-xs animate-pulse">
          ● Live (refresh ทุก 15 วินาที)
        </Badge>
      </div>

      {/* Real-time agency cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {data.agencies.map(a => (
          <Card key={a.id} className="relative overflow-hidden">
            <div
              className="absolute top-0 left-0 right-0 h-1"
              style={{ background: STATUS_COLORS[a.status] }}
            />
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">{a.name}</CardTitle>
                {a.status === 'healthy' && <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
                {a.status === 'degraded' && <AlertCircle className="h-4 w-4 text-amber-500" />}
                {a.status === 'down' && <XCircle className="h-4 w-4 text-red-500" />}
              </div>
              <CardDescription className="text-xs">{a.shortName}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs text-muted-foreground">Uptime</span>
                <span className="font-mono font-semibold">{a.uptime}%</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-muted-foreground flex items-center gap-1"><Zap className="h-3 w-3" /> Latency</span>
                <span className="font-mono font-semibold">{a.currentLatency}ms</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-muted-foreground">Error Rate</span>
                <span className="font-mono">{a.errorRate}%</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-muted-foreground">Req/min</span>
                <span className="font-mono">{a.requestsPerMin}</span>
              </div>
              <Badge
                className="w-full justify-center mt-2"
                style={{ background: STATUS_COLORS[a.status], color: 'white' }}
              >
                {STATUS_LABELS[a.status]}
              </Badge>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Historical Latency Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Latency 24 ชั่วโมงย้อนหลัง</CardTitle>
          <CardDescription>หน่วย: มิลลิวินาที (ms)</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={data.historical}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="time" stroke="hsl(var(--muted-foreground))" fontSize={11} />
              <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} unit="ms" />
              <Tooltip contentStyle={{ background: 'hsl(var(--background))', border: '1px solid hsl(var(--border))', borderRadius: 8 }} />
              <Legend />
              {data.agencies.map((a, i) => (
                <Line
                  key={a.id}
                  type="monotone"
                  dataKey={`${a.id}_latency`}
                  name={a.shortName}
                  stroke={AGENCY_COLORS[i]}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}

export default function HealthPage() {
  const { data, isLoading, isError, refetch } = useAgencyHealth();

  return (
    <QueryStateBoundary
      isLoading={isLoading}
      isError={isError}
      hasData={!!data}
      onRetry={() => void refetch()}
    >
      {data && <HealthContent data={data} />}
    </QueryStateBoundary>
  );
}
