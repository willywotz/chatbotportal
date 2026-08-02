import { useState } from 'react';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/shared/components/ui/table';
import { Input } from '@/shared/components/ui/input';
import { BarChart3 } from 'lucide-react';
import { useUsage } from './useUsage';

export default function UsageAnalyticsPage() {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const { data, isLoading, isError } = useUsage({
    group_by: 'api_key',
    from: from ? new Date(from).toISOString() : undefined,
    // exclusive upper bound = start of the day after the selected date, so the picked "to" day is included
    to: to ? new Date(new Date(to).getTime() + 24 * 60 * 60 * 1000).toISOString() : undefined,
  });

  const rows = data ?? [];

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div className="flex items-center gap-2">
        <BarChart3 className="h-5 w-5 text-primary" />
        <h1 className="text-2xl">การใช้งานต่อ API Key</h1>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted-foreground">ตั้งแต่</label>
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="max-w-[12rem]" />
        <label className="text-sm text-muted-foreground">ถึง</label>
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="max-w-[12rem]" />
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>API Key</TableHead>
            <TableHead>เจ้าของ</TableHead>
            <TableHead className="text-right">Prompt</TableHead>
            <TableHead className="text-right">Completion</TableHead>
            <TableHead className="text-right">รวม</TableHead>
            <TableHead className="text-right">ค่าใช้จ่าย (USD)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading && (
            <TableRow><TableCell colSpan={6}>กำลังโหลด...</TableCell></TableRow>
          )}
          {isError && !isLoading && (
            <TableRow><TableCell colSpan={6}>เกิดข้อผิดพลาดในการโหลดข้อมูล</TableCell></TableRow>
          )}
          {!isLoading && !isError && rows.length === 0 && (
            <TableRow><TableCell colSpan={6}>ไม่พบข้อมูล</TableCell></TableRow>
          )}
          {rows.map((r) => (
            <TableRow key={r.key}>
              <TableCell>
                <div className="font-medium">{r.name ?? r.key}</div>
                {r.key_prefix && r.key_prefix !== '—' && (
                  <div className="text-xs text-muted-foreground">{r.key_prefix}</div>
                )}
              </TableCell>
              <TableCell className="text-sm">{r.owner_email ?? '—'}</TableCell>
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
