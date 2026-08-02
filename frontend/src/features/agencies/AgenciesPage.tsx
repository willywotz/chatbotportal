import { Plus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import type { Agency, AgencyLifecycleStatus } from "@/shared/types/agency";

import { AgencyCard } from "./AgencyCard";
import type { TestResult } from "./ConnectionTestResult";
import { DeleteAgencyDialog } from "./DeleteAgencyDialog";
import { STATUS_LABEL } from "./lifecycle";
import {
  useAgencies,
  useDeleteAgency,
  useTestConnection,
  useUpdateAgencyStatus,
} from "./useAgencies";

type StatusFilter = AgencyLifecycleStatus | "all";
type TypeFilter = Agency["connectionType"] | "all";

const STATUS_FILTERS: StatusFilter[] = ["all", "active", "draft", "maintenance", "disabled"];
const TYPE_FILTERS: TypeFilter[] = ["all", "API", "MCP", "A2A"];

export default function AgenciesPage() {
  const { data: agencies = [], isLoading } = useAgencies();
  const deleteMutation = useDeleteAgency();
  const testMutation = useTestConnection();
  const statusMutation = useUpdateAgencyStatus();

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [search, setSearch] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Agency | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestResult | null>>({});

  const filtered = useMemo(
    () =>
      agencies.filter((a) => {
        if (statusFilter !== "all" && a.status !== statusFilter) return false;
        if (typeFilter !== "all" && a.connectionType !== typeFilter) return false;
        const q = search.trim().toLowerCase();
        if (q && !`${a.name} ${a.shortName} ${a.description}`.toLowerCase().includes(q)) return false;
        return true;
      }),
    [agencies, statusFilter, typeFilter, search],
  );

  const handleTest = useCallback(async (agency: Agency) => {
    setTestingId(agency.id);
    setTestResults((prev) => ({ ...prev, [agency.id]: null }));
    try {
      const result = await testMutation.mutateAsync({ agencyId: agency.id });
      setTestResults((prev) => ({ ...prev, [agency.id]: result }));
    } catch (err: unknown) {
      setTestResults((prev) => ({
        ...prev,
        [agency.id]: { success: false, error: err instanceof Error ? err.message : "Connection failed" },
      }));
    } finally {
      setTestingId(null);
    }
  }, [testMutation]);

  const handleStatusChange = useCallback(async (agency: Agency, status: AgencyLifecycleStatus) => {
    try {
      await statusMutation.mutateAsync({ id: agency.id, status });
      toast.success(`เปลี่ยนสถานะเป็น ${STATUS_LABEL[status]} สำเร็จ`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    }
  }, [statusMutation]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMutation.mutateAsync(deleteTarget.id);
      toast.success("ลบหน่วยงานสำเร็จ");
      setDeleteTarget(null);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    }
  };

  return (
    <div className="p-4 md:p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg text-foreground">จัดการหน่วยงานที่เชื่อมต่อ</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            รองรับ MCP, A2A และ API สำหรับการสื่อสารระหว่าง AI Agent
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{filtered.length} หน่วยงาน</span>
          <Button size="sm" asChild>
            <Link to="/agencies/new">
              <Plus className="h-4 w-4 mr-1" /> เพิ่มหน่วยงาน
            </Link>
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {STATUS_FILTERS.map((s) => (
          <Button
            key={s}
            size="sm"
            variant={statusFilter === s ? "default" : "outline"}
            onClick={() => setStatusFilter(s)}
          >
            {s === "all" ? "ทั้งหมด" : STATUS_LABEL[s]}
          </Button>
        ))}
        <span className="mx-1 h-4 w-px bg-border" />
        {TYPE_FILTERS.map((t) => (
          <Button
            key={t}
            size="sm"
            variant={typeFilter === t ? "default" : "outline"}
            onClick={() => setTypeFilter(t)}
          >
            {t === "all" ? "ทุกประเภท" : t}
          </Button>
        ))}
        <Input
          placeholder="ค้นหาหน่วยงาน…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 w-48 ml-auto"
        />
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-muted-foreground">กำลังโหลด...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">ไม่พบหน่วยงาน</div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {filtered.map((agency) => (
            <AgencyCard
              key={agency.id}
              agency={agency}
              onTest={handleTest}
              onDelete={setDeleteTarget}
              onStatusChange={handleStatusChange}
              testing={testingId === agency.id}
              testResult={testResults[agency.id] ?? null}
            />
          ))}
        </div>
      )}

      <DeleteAgencyDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        agencyName={deleteTarget?.name || ""}
        onConfirm={handleDelete}
        deleting={deleteMutation.isPending}
      />
    </div>
  );
}
