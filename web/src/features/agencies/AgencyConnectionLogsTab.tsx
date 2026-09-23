import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Badge } from "@/shared/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/components/ui/table";
import { format } from "date-fns";
import type { ConnectionLogResponse } from "@/features/connection-logs/useConnectionLogs";

const statusColors: Record<string, string> = {
  success: "text-green-600 dark:text-green-400",
  error: "text-destructive",
};

interface Props {
  logs: ConnectionLogResponse;
  logsLoading: boolean;
}

export function AgencyConnectionLogsTab({ logs, logsLoading }: Props) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">ประวัติการเชื่อมต่อล่าสุด</CardTitle>
      </CardHeader>
      <CardContent>
        {logsLoading ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : logs.total_connections === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">ยังไม่มีประวัติการเชื่อมต่อ</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[140px]">เวลา</TableHead>
                <TableHead className="w-[80px]">ประเภท</TableHead>
                <TableHead className="w-[80px]">สถานะ</TableHead>
                <TableHead className="w-[100px]">Latency</TableHead>
                <TableHead>รายละเอียด</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.items.map((log) => (
                <TableRow key={log.id}>
                  <TableCell className="text-xs font-mono text-muted-foreground">
                    {format(new Date(log.created_at), "dd/MM HH:mm:ss")}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-[10px]">{log.action}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className={`text-xs font-medium ${statusColors[log.status] || ""}`}>
                      {log.status === "success" ? "✓ สำเร็จ" : "✗ ล้มเหลว"}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs font-mono">{log.latency_ms} ms</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{log.detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
