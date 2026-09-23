import { Pencil, Trash2 } from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import type { LlmProvider } from "./llmProviderApi";

interface Props {
  providers: LlmProvider[];
  onEdit: (provider: LlmProvider) => void;
  onDelete: (provider: LlmProvider) => void;
}

export function LlmProviderList({ providers, onEdit, onDelete }: Props) {
  if (providers.length === 0) {
    return (
      <p className="text-center text-sm text-muted-foreground py-12">
        ยังไม่มีผู้ให้บริการ LLM กรุณาเพิ่มใหม่
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {providers.map((p) => (
        <Card key={p.id}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-foreground truncate">{p.name}</p>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      p.enabled
                        ? "bg-green-100 text-green-700"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {p.enabled ? "เปิดใช้งาน" : "ปิดใช้งาน"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground font-mono mt-1 truncate">
                  {p.base_url}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  Auth: {p.auth_header} ({p.auth_scheme}) · Key: {p.api_key}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  หมดเวลา {p.timeout_seconds}s · คิวสูงสุด {p.max_queue_size}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  จำกัดอัตรา{" "}
                  {p.rate_limit_rps != null ? `${p.rate_limit_rps} ครั้ง/วินาที` : "—"} /{" "}
                  {p.rate_limit_rpm != null ? `${p.rate_limit_rpm} ครั้ง/นาที` : "—"}
                  {" · บันทึกการใช้งาน "}
                  {p.request_usage ? "เปิด" : "ปิด"}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => onEdit(p)}
                  className="p-1.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="แก้ไข"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => onDelete(p)}
                  className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                  aria-label="ลบ"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
