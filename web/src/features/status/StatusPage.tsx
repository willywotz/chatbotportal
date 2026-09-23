import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/lib/apiClient';
import { Badge } from '@/shared/components/ui/badge';
import { REFETCH } from '@/shared/constants/query';
import { PUBLIC_STATUS_LABEL as STATUS_LABEL, PUBLIC_STATUS_VARIANT as STATUS_VARIANT } from '@/shared/constants/status';

interface PublicStatus {
  name: string;
  status: string;
  uptime_24h_pct: number | null;
}

function fetchPublicStatus(): Promise<PublicStatus[]> {
  return api.get<PublicStatus[]>('/api/v1/public/status');
}

export default function StatusPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['public-status'],
    queryFn: fetchPublicStatus,
    refetchInterval: REFETCH.slow,
  });

  const rows = data ?? [];

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b border-border bg-card/80 backdrop-blur-sm px-6 py-3 flex items-center gap-2.5">
        <span className="font-semibold text-foreground">สถานะระบบหน่วยงาน</span>
      </header>

      <main className="flex-1 p-6 max-w-3xl mx-auto w-full">
        {isLoading && <p className="text-sm text-muted-foreground">กำลังโหลด…</p>}
        {isError && <p className="text-sm text-destructive">ไม่สามารถโหลดสถานะได้</p>}

        {!isLoading && !isError && (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">หน่วยงาน</th>
                  <th className="px-4 py-2 font-medium">สถานะ</th>
                  <th className="px-4 py-2 font-medium">ความพร้อมใช้งาน 24 ชม.</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.name} className="border-t border-border">
                    <td className="px-4 py-3 font-medium text-foreground">{row.name}</td>
                    <td className="px-4 py-3">
                      <Badge variant={STATUS_VARIANT[row.status] ?? 'outline'}>
                        {STATUS_LABEL[row.status] ?? row.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      {row.uptime_24h_pct === null ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-32 overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${row.uptime_24h_pct}%` }}
                            />
                          </div>
                          <span className="tabular-nums text-foreground">{row.uptime_24h_pct}%</span>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-4 py-6 text-center text-muted-foreground">
                      ไม่มีข้อมูลหน่วยงาน
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
