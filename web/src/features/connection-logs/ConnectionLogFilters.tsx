import { Input } from "@/shared/components/ui/input";
import { Button } from "@/shared/components/ui/button";
import { Search, X } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import type { Agency } from "@/shared/types";

interface Props {
  search: string;
  filterStatus: string | null;
  filterType: string | null;
  filterAgency: string | null;
  agencies: Agency[];
  hasFilters: boolean;
  onSearchChange: (v: string) => void;
  onStatusChange: (v: string | null) => void;
  onTypeChange: (v: string | null) => void;
  onAgencyChange: (v: string | null) => void;
  onReset: () => void;
  includeTest: boolean;
  onIncludeTestChange: (v: boolean) => void;
}

export function ConnectionLogFilters({
  search, filterStatus, filterType, filterAgency, agencies, hasFilters,
  onSearchChange, onStatusChange, onTypeChange, onAgencyChange, onReset,
  includeTest, onIncludeTestChange,
}: Props) {
  return (
    <div className="flex flex-wrap gap-2 items-center">
      <div className="relative flex-1 min-w-[180px]">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="ค้นหา detail..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9 h-8 text-sm"
        />
      </div>
      <div className="flex gap-1">
        {([null, "success", "error"] as const).map((s) => (
          <button
            key={s ?? "all"}
            onClick={() => onStatusChange(s)}
            className={cn(
              "text-xs px-3 py-1.5 rounded-full border transition-colors",
              filterStatus === s ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:bg-accent"
            )}
          >
            {s === null ? "ทั้งหมด" : s === "success" ? "สำเร็จ" : "ล้มเหลว"}
          </button>
        ))}
      </div>
      <div className="flex gap-1">
        {["MCP", "API", "A2A"].map((t) => (
          <button
            key={t}
            onClick={() => onTypeChange(filterType === t ? null : t)}
            className={cn(
              "text-xs px-3 py-1.5 rounded-full border transition-colors",
              filterType === t ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:bg-accent"
            )}
          >
            {t}
          </button>
        ))}
      </div>
      <button
        onClick={() => onIncludeTestChange(!includeTest)}
        className={cn(
          "text-xs px-3 py-1.5 rounded-full border transition-colors",
          includeTest ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:bg-accent"
        )}
      >
        แสดงการทดสอบ
      </button>
      {agencies.length > 0 && (
        <select
          value={filterAgency ?? ""}
          onChange={(e) => onAgencyChange(e.target.value || null)}
          className="text-xs h-8 px-2 rounded-md border border-border bg-background text-foreground"
        >
          <option value="">หน่วยงานทั้งหมด</option>
          {agencies.map((a) => <option key={a.id} value={a.id}>{a.shortName}</option>)}
        </select>
      )}
      {hasFilters && (
        <Button variant="ghost" size="sm" className="h-8 text-xs text-muted-foreground" onClick={onReset}>
          <X className="h-3.5 w-3.5 mr-1" /> ล้างตัวกรอง
        </Button>
      )}
    </div>
  );
}
