import { useUsageHeatmap } from './useHeatmap';
import type { HeatmapRange, UsageHeatmapData } from './heatmapApi';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/components/ui/card';
import { PageHeader } from '@/shared/components/layout/PageHeader';
import { Badge } from '@/shared/components/ui/badge';
import { QueryStateBoundary } from '@/shared/components/QueryStateBoundary';
import { ToggleGroup, ToggleGroupItem } from '@/shared/components/ui/toggle-group';
import { Flame, Clock, TrendingUp, Database } from 'lucide-react';
import { useMemo, useState } from 'react';

function getColor(value: number, max: number) {
  if (max === 0) return 'hsl(213 30% 95%)';
  const intensity = value / max;
  if (intensity === 0) return 'hsl(213 30% 96%)';
  // Light blue → primary blue → deep red gradient
  if (intensity < 0.25) return `hsl(213 70% ${92 - intensity * 80}%)`;
  if (intensity < 0.5) return `hsl(213 75% ${75 - intensity * 50}%)`;
  if (intensity < 0.75) return `hsl(25 85% ${65 - intensity * 20}%)`;
  return `hsl(0 75% ${60 - intensity * 15}%)`;
}

function HeatmapContent({
  data,
  range,
  setRange,
}: {
  data: UsageHeatmapData;
  range: HeatmapRange;
  setRange: (r: HeatmapRange) => void;
}) {
  const maxDayHour = useMemo(
    () => Math.max(...data.dayHourMatrix.flatMap(r => r.data)),
    [data],
  );

  const maxAgencyHour = useMemo(
    () => Math.max(...data.hourlyByAgency.flatMap(r => r.data)),
    [data],
  );

  return (
    <div className="p-6 space-y-6 mx-auto">
      <PageHeader
        icon={<Flame className="h-7 w-7 text-orange-500" />}
        title="Usage Heatmap"
        subtitle="ปริมาณคำถามตามช่วงเวลา-หน่วยงาน จากข้อมูลจริง"
        actions={
          <div className="flex items-center gap-3">
          <Badge variant="outline" className="text-xs flex items-center gap-1">
            <Database className="h-3 w-3" />
            {data.sampleSize.toLocaleString()} conversations · {data.totalMessages.toLocaleString()} messages
          </Badge>
          <ToggleGroup
            type="single"
            value={range}
            onValueChange={(v) => v && setRange(v as HeatmapRange)}
            variant="outline"
            size="sm"
          >
            <ToggleGroupItem value="7d">7 วัน</ToggleGroupItem>
            <ToggleGroupItem value="30d">30 วัน</ToggleGroupItem>
            <ToggleGroupItem value="90d">90 วัน</ToggleGroupItem>
          </ToggleGroup>
          </div>
        }
      />

      {/* Insights */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Peak Day</CardDescription>
            <CardTitle className="text-2xl">{data.insights.peakDay}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">วันที่ใช้งานสูงสุด</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Peak Hour</CardDescription>
            <CardTitle className="text-2xl flex items-center gap-2">
              <Clock className="h-5 w-5 text-primary" />
              {data.insights.peakHour}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">{data.insights.peakValue.toLocaleString()} คำถาม</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Business Hours (8-18)</CardDescription>
            <CardTitle className="text-2xl text-primary">{data.insights.businessHoursPercent}%</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">ของปริมาณทั้งหมด</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Busiest Agency</CardDescription>
            <CardTitle className="text-xl flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-orange-500" />
              {data.insights.busiest.agency}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">Peak {String(data.insights.busiest.peakHour).padStart(2, '0')}:00</p>
          </CardContent>
        </Card>
      </div>

      {/* Day x Hour Heatmap */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Heatmap วัน × ชั่วโมง (ภาพรวม)</CardTitle>
          <CardDescription>เข้มขึ้น = คำถามมากขึ้น</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <div className="min-w-[900px]">
            {/* Hour labels */}
            <div className="flex">
              <div className="w-20 shrink-0" />
              {data.hours.map(h => (
                <div key={h} className="flex-1 text-center text-[10px] text-muted-foreground font-mono">
                  {h % 3 === 0 ? String(h).padStart(2, '0') : ''}
                </div>
              ))}
            </div>
            {data.dayHourMatrix.map(row => (
              <div key={row.day} className="flex items-center mt-4">
                <div className="w-20 shrink-0 text-xs font-medium text-right pr-3">{row.day}</div>
                {row.data.map((v, h) => (
                  <div
                    key={h}
                    className="flex-1 aspect-square rounded-sm mx-px transition hover:ring-2 hover:ring-primary cursor-pointer relative group"
                    style={{ background: getColor(v, maxDayHour) }}
                    title={`${row.day} ${String(h).padStart(2, '0')}:00 — ${v.toLocaleString()} คำถาม`}
                  >
                    <div className="absolute hidden group-hover:block bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-popover border rounded text-[10px] whitespace-nowrap z-10 shadow-lg">
                      {v.toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            ))}

            {/* Legend */}
            <div className="flex items-center gap-2 mt-4 text-xs">
              <span className="text-muted-foreground">น้อย</span>
              <div className="flex">
                {[0, 0.2, 0.4, 0.6, 0.8, 1].map(i => (
                  <div key={i} className="w-6 h-3" style={{ background: getColor(i * maxDayHour, maxDayHour) }} />
                ))}
              </div>
              <span className="text-muted-foreground">มาก</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Agency x Hour Heatmap */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Heatmap หน่วยงาน × ชั่วโมง</CardTitle>
          <CardDescription>เปรียบเทียบ pattern การใช้งานของแต่ละหน่วยงาน</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <div className="min-w-[900px]">
            <div className="flex">
              <div className="w-32 shrink-0" />
              {data.hours.map(h => (
                <div key={h} className="flex-1 text-center text-[10px] text-muted-foreground font-mono">
                  {h % 3 === 0 ? String(h).padStart(2, '0') : ''}
                </div>
              ))}
            </div>
            {data.hourlyByAgency.map(row => (
              <div key={row.agencyId} className="flex items-center mt-4">
                <div className="w-32 shrink-0 text-xs font-medium text-right pr-3">{row.agency}</div>
                {row.data.map((v, h) => (
                  <div
                    key={h}
                    className="flex-1 aspect-square rounded-sm mx-px transition hover:ring-2 hover:ring-primary cursor-pointer relative group"
                    style={{ background: getColor(v, maxAgencyHour) }}
                    title={`${row.agency} ${String(h).padStart(2, '0')}:00 — ${v.toLocaleString()}`}
                  >
                    <div className="absolute hidden group-hover:block bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-popover border rounded text-[10px] whitespace-nowrap z-10 shadow-lg">
                      {v.toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function HeatmapPage() {
  const [range, setRange] = useState<HeatmapRange>('7d');
  const { data, isLoading, isError, refetch } = useUsageHeatmap(range);

  return (
    <QueryStateBoundary
      isLoading={isLoading}
      isError={isError}
      hasData={!!data}
      onRetry={() => void refetch()}
    >
      {data && <HeatmapContent data={data} range={range} setRange={setRange} />}
    </QueryStateBoundary>
  );
}
