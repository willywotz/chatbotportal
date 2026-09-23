import { useState } from 'react';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/shared/components/ui/table';
import { Input } from '@/shared/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/shared/components/ui/tabs';
import { PageHeader } from '@/shared/components/layout/PageHeader';
import { BarChart3 } from 'lucide-react';
import { useUsage } from './useUsage';
import type { UsageParams } from './usageApi';

const GROUP_TABS: { label: string; value: UsageParams['group_by'] }[] = [
  { label: 'ตามวัตถุประสงค์', value: 'purpose' },
  { label: 'ตามโมเดล', value: 'model' },
  { label: 'ตามผู้ใช้', value: 'user' },
];

export default function UsageAnalyticsPage() {
  const [groupBy, setGroupBy] = useState<UsageParams['group_by']>('purpose');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const { data, isLoading, isError } = useUsage({
    group_by: groupBy,
    from: from ? new Date(from).toISOString() : undefined,
    // exclusive upper bound = start of the day after the selected date, so the picked "to" day is included
    to: to ? new Date(new Date(to).getTime() + 24 * 60 * 60 * 1000).toISOString() : undefined,
  });

  const rows = data ?? [];

  return (
    <div className="p-4 md:p-6 space-y-4">
      <PageHeader icon={<BarChart3 className="h-5 w-5 text-primary" />} title="การใช้งาน" />

      <Tabs value={groupBy} onValueChange={(v) => setGroupBy(v as UsageParams['group_by'])}>
        <TabsList>
          {GROUP_TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted-foreground">ตั้งแต่</label>
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="max-w-[12rem]" />
        <label className="text-sm text-muted-foreground">ถึง</label>
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="max-w-[12rem]" />
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{GROUP_TABS.find((t) => t.value === groupBy)?.label}</TableHead>
            <TableHead className="text-right">Prompt</TableHead>
            <TableHead className="text-right">Completion</TableHead>
            <TableHead className="text-right">รวม</TableHead>
            <TableHead className="text-right">ค่าใช้จ่าย (USD)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading && (
            <TableRow><TableCell colSpan={5}>กำลังโหลด...</TableCell></TableRow>
          )}
          {isError && !isLoading && (
            <TableRow><TableCell colSpan={5}>เกิดข้อผิดพลาดในการโหลดข้อมูล</TableCell></TableRow>
          )}
          {!isLoading && !isError && rows.length === 0 && (
            <TableRow><TableCell colSpan={5}>ไม่พบข้อมูล</TableCell></TableRow>
          )}
          {rows.map((r) => (
            <TableRow key={r.key}>
              <TableCell className="font-medium">{r.key}</TableCell>
              <TableCell className="text-right tabular-nums">{r.prompt_tokens.toLocaleString()}</TableCell>
              <TableCell className="text-right tabular-nums">{r.completion_tokens.toLocaleString()}</TableCell>
              <TableCell className="text-right tabular-nums">
                {(r.prompt_tokens + r.completion_tokens).toLocaleString()}
              </TableCell>
              <TableCell className="text-right tabular-nums">${r.cost_usd.toFixed(6)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
