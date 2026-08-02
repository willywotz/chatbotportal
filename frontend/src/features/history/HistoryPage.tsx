import { useState } from "react";
import { Card, CardContent } from "@/shared/components/ui/card";
import { PageHeader } from "@/shared/components/layout/PageHeader";
import { Input } from "@/shared/components/ui/input";
import { Badge } from "@/shared/components/ui/badge";
import { Search, CheckCircle, XCircle, Loader2, Trash2, Download, FileText, CalendarIcon, X, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Calendar } from "@/shared/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/shared/components/ui/alert-dialog";
import { useChatHistory } from "@/features/history/useChatHistory";
import { ConversationDetailDialog } from "@/features/history/ConversationDetailDialog";
import { deleteConversation } from "@/features/history/historyApi";
import type { HistoryItem } from "@/features/history/historyApi";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { exportToCsv, exportToPdf } from "@/features/history/exportHistory";
import { format } from "date-fns";
import { th } from "date-fns/locale";
import { cn } from "@/shared/lib/utils";
import { getPaginationRange } from "@/shared/lib/pagination";
import type { DateRange } from "react-day-picker";
import { PAGE_SIZE as PAGE_SIZES } from "@/shared/constants/query";

const PAGE_SIZE = PAGE_SIZES.history;

export default function HistoryPage() {
  const [search, setSearch] = useState("");
  const [filterAgency, setFilterAgency] = useState<string | null>(null);
  const [selectedConv, setSelectedConv] = useState<HistoryItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<HistoryItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();

  const dateFrom = dateRange?.from ? format(dateRange.from, "yyyy-MM-dd") : undefined;
  const dateTo = dateRange?.to ? format(dateRange.to, "yyyy-MM-dd") : undefined;

  const { data, isLoading } = useChatHistory({
    search: search || undefined,
    filterAgency: filterAgency || undefined,
    dateFrom,
    dateTo,
    page,
    pageSize: PAGE_SIZE,
  });

  const conversations = data?.data ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    const ok = await deleteConversation(deleteTarget.id);
    setDeleting(false);
    setDeleteTarget(null);
    if (ok) {
      toast.success("ลบสนทนาเรียบร้อย");
      queryClient.invalidateQueries({ queryKey: ['chatHistory'] });
    } else {
      toast.error("ไม่สามารถลบได้ กรุณาลองใหม่");
    }
  };

  return (
    <div className="p-4 md:p-6 space-y-4">
      <PageHeader
        title="ประวัติการสนทนา"
        actions={
          conversations.length > 0 && (
            <div className="flex gap-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => { exportToCsv(conversations); toast.success("ส่งออก CSV เรียบร้อย"); }}
              >
                <Download className="h-3.5 w-3.5 mr-1" />
                CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => { exportToPdf(conversations); toast.success("ส่งออก PDF เรียบร้อย"); }}
              >
                <FileText className="h-3.5 w-3.5 mr-1" />
                PDF
              </Button>
            </div>
          )
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="ค้นหาการสนทนา..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="pl-9"
          />
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={() => { setFilterAgency(null); setPage(1); }}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${!filterAgency ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground hover:bg-accent'}`}
          >
            ทั้งหมด
          </button>
        </div>

        {/* Date range picker */}
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className={cn(
                "text-xs gap-1.5",
                !dateRange?.from && "text-muted-foreground"
              )}
            >
              <CalendarIcon className="h-3.5 w-3.5" />
              {dateRange?.from ? (
                dateRange.to ? (
                  <>{format(dateRange.from, "d MMM", { locale: th })} – {format(dateRange.to, "d MMM", { locale: th })}</>
                ) : (
                  format(dateRange.from, "d MMM yyyy", { locale: th })
                )
              ) : (
                "เลือกช่วงวันที่"
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="range"
              selected={dateRange}
              onSelect={(r) => { setDateRange(r); setPage(1); }}
              numberOfMonths={2}
              initialFocus
              className={cn("p-3 pointer-events-auto")}
            />
          </PopoverContent>
        </Popover>

        {dateRange?.from && (
          <Button
            variant="ghost"
            size="sm"
            className="text-xs h-8 px-2 text-muted-foreground"
            onClick={() => { setDateRange(undefined); setPage(1); }}
          >
            <X className="h-3.5 w-3.5 mr-1" />
            ล้างวันที่
          </Button>
        )}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {/* Conversation list */}
      {!isLoading && (
        <div className="space-y-2">
          {conversations.map((conv) => (
            <Card key={conv.id} className="cursor-pointer hover:bg-accent/30 transition-colors" onClick={() => setSelectedConv(conv)}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {conv.status === 'success' ? (
                        <CheckCircle className="h-4 w-4 text-green-600 shrink-0" />
                      ) : (
                        <XCircle className="h-4 w-4 text-destructive shrink-0" />
                      )}
                      <h3 className="text-sm font-medium text-foreground truncate">{conv.title}</h3>
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-1 ml-6">{conv.preview}</p>
                    <div className="flex items-center gap-2 mt-2 ml-6 flex-wrap">
                      {conv.agencies.map((a, i) => (
                        <Badge key={i} variant="outline" className="text-[10px]">{a}</Badge>
                      ))}
                      {conv.messageCount && (
                        <span className="text-[10px] text-muted-foreground">{conv.messageCount} ข้อความ</span>
                      )}
                      {conv.responseTime && (
                        <span className="text-[10px] text-muted-foreground">⏱ {conv.responseTime}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <span className="text-[10px] text-muted-foreground">{conv.date}</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeleteTarget(conv); }}
                      className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                      aria-label="ลบสนทนา"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
          {total === 0 && (
            <p className="text-center text-sm text-muted-foreground py-12">ไม่พบผลลัพธ์</p>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <span className="text-xs text-muted-foreground">
                แสดง {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, total)} จาก {total} รายการ
              </span>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  disabled={safePage <= 1}
                  onClick={() => setPage(safePage - 1)}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                {getPaginationRange(safePage, totalPages).map((p, i) =>
                  p === "ellipsis" ? (
                    <span key={`ellipsis-${i}`} className="px-1 text-xs text-muted-foreground">…</span>
                  ) : (
                    <Button
                      key={p}
                      variant={p === safePage ? "default" : "outline"}
                      size="icon"
                      className="h-8 w-8 text-xs"
                      onClick={() => setPage(p)}
                    >
                      {p}
                    </Button>
                  ),
                )}
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  disabled={safePage >= totalPages}
                  onClick={() => setPage(safePage + 1)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      <ConversationDetailDialog
        conversation={selectedConv}
        open={!!selectedConv}
        onOpenChange={(open) => { if (!open) setSelectedConv(null); }}
      />

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>ยืนยันการลบ</AlertDialogTitle>
            <AlertDialogDescription>
              ต้องการลบสนทนา "{deleteTarget?.title}" หรือไม่? การดำเนินการนี้ไม่สามารถย้อนกลับได้
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>ยกเลิก</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              ลบ
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
