import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/shared/components/ui/dialog";
import { Button } from "@/shared/components/ui/button";
import { AlertCircle, CheckCircle2, XCircle, Loader2, ChevronLeft, ChevronRight } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/shared/lib/utils";
import type { ConnectionLog } from "@/shared/types/connectionLog";

const connectionTypeColors: Record<string, string> = {
  MCP: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  API: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  A2A: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

interface Props {
  items: ConnectionLog[];
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
  agencyMap: Record<string, string>;
  selectedLog: ConnectionLog | null;
  onSelectLog: (log: ConnectionLog) => void;
  onCloseLog: () => void;
  page: number;
  totalPages: number;
  totalItems: number;
  onPageChange: (p: number) => void;
}

export function ConnectionLogsTable({
  items, isLoading, isError = false, onRetry, agencyMap, selectedLog, onSelectLog, onCloseLog,
  page, totalPages, totalItems, onPageChange,
}: Props) {
  return (
    <>
      {isLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[130px]">วันที่/เวลา</TableHead>
                <TableHead>หน่วยงาน</TableHead>
                <TableHead className="w-[80px]">ประเภท</TableHead>
                <TableHead className="w-[70px]">Action</TableHead>
                <TableHead className="w-[80px]">สถานะ</TableHead>
                <TableHead className="w-[80px] text-right">Latency</TableHead>
                <TableHead>รายละเอียด</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isError ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-10">
                    <div role="alert" aria-live="assertive" className="flex flex-col items-center justify-center gap-2 text-destructive text-sm">
                      <div className="flex items-center gap-2">
                        <AlertCircle className="h-4 w-4 shrink-0" />
                        <span>เกิดข้อผิดพลาดในการโหลดข้อมูล</span>
                      </div>
                      {onRetry && (
                        <Button variant="outline" size="sm" onClick={onRetry}>ลองอีกครั้ง</Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground py-10 text-sm">ไม่พบข้อมูล</TableCell>
                </TableRow>
              ) : items.map((log) => (
                <TableRow key={log.id} className="cursor-pointer hover:bg-accent/50" onClick={() => onSelectLog(log)}>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {format(new Date(log.created_at), "dd/MM/yy HH:mm:ss")}
                  </TableCell>
                  <TableCell className="text-xs font-medium whitespace-nowrap">
                    {agencyMap[log.agency_id] || (log.agency_id ? log.agency_id.slice(0, 8) : "—")}
                  </TableCell>
                  <TableCell className="text-xs whitespace-nowrap">
                    <span className={cn("text-[10px] px-2 py-0.5 rounded-full font-medium", connectionTypeColors[log.connection_type] || "bg-muted text-muted-foreground")}>
                      {log.connection_type}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs capitalize text-muted-foreground whitespace-nowrap">{log.action}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">
                    {log.status === "success" ? (
                      <span className="flex items-center gap-1 text-green-600 dark:text-green-400 text-xs"><CheckCircle2 className="h-3.5 w-3.5" /> สำเร็จ</span>
                    ) : (
                      <span className="flex items-center gap-1 text-destructive text-xs"><XCircle className="h-3.5 w-3.5" /> ล้มเหลว</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-right tabular-nums whitespace-nowrap">
                    <span className={cn(log.latency_ms > 1000 ? "text-amber-600" : "text-muted-foreground")}>{log.latency_ms} ms</span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate whitespace-nowrap" title={log.detail}>{log.detail || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-1">
          <span className="text-xs text-muted-foreground">หน้า {page}/{totalPages} · {totalItems} รายการ</span>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" className="h-7 w-7" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              const p = totalPages <= 7 ? i + 1 : page <= 4 ? i + 1 : page >= totalPages - 3 ? totalPages - 6 + i : page - 3 + i;
              return (
                <Button key={p} variant={p === page ? "default" : "outline"} size="icon" className="h-7 w-7 text-xs" onClick={() => onPageChange(p)}>{p}</Button>
              );
            })}
            <Button variant="outline" size="icon" className="h-7 w-7" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <Dialog open={!!selectedLog} onOpenChange={(o) => { if (!o) onCloseLog(); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              {selectedLog?.status === "success" ? <CheckCircle2 className="h-4 w-4 text-green-600" /> : <XCircle className="h-4 w-4 text-destructive" />}
              Connection Log Detail
            </DialogTitle>
          </DialogHeader>
          {selectedLog && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div><p className="text-xs text-muted-foreground">วันที่/เวลา</p><p className="font-medium text-xs">{format(selectedLog.created_at, "dd/MM/yyyy HH:mm:ss")}</p></div>
                <div><p className="text-xs text-muted-foreground">หน่วยงาน</p><p className="font-medium text-xs">{agencyMap[selectedLog.agency_id] || selectedLog.agency_id || "—"}</p></div>
                <div>
                  <p className="text-xs text-muted-foreground">ประเภทการเชื่อมต่อ</p>
                  <span className={cn("text-[10px] px-2 py-0.5 rounded-full font-medium", connectionTypeColors[selectedLog.connection_type] || "bg-muted text-muted-foreground")}>{selectedLog.connection_type}</span>
                </div>
                <div><p className="text-xs text-muted-foreground">Action</p><p className="font-medium text-xs capitalize">{selectedLog.action}</p></div>
                <div>
                  <p className="text-xs text-muted-foreground">สถานะ</p>
                  {selectedLog.status === "success"
                    ? <span className="flex items-center gap-1 text-green-600 dark:text-green-400 text-xs font-medium"><CheckCircle2 className="h-3.5 w-3.5" /> สำเร็จ</span>
                    : <span className="flex items-center gap-1 text-destructive text-xs font-medium"><XCircle className="h-3.5 w-3.5" /> ล้มเหลว</span>}
                </div>
                <div><p className="text-xs text-muted-foreground">Latency</p><p className={cn("font-medium text-xs", selectedLog.latency_ms > 15_000 ? "text-amber-600" : "")}>{selectedLog.latency_ms} ms</p></div>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-1">รายละเอียด</p>
                <pre className="text-xs bg-muted rounded-md p-3 whitespace-pre-wrap break-all font-mono leading-relaxed max-h-48 overflow-y-auto">{selectedLog.detail || "—"}</pre>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
