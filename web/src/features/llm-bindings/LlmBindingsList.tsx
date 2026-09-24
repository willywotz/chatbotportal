import { CheckCircle2, Loader2, Pencil, XCircle } from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import type { LlmBinding, LlmBindingTestResult } from "./llmBindingApi";

export interface BindingTestState {
  loading: boolean;
  result?: LlmBindingTestResult;
}

interface Props {
  bindings: LlmBinding[];
  onEdit: (binding: LlmBinding) => void;
  onTest: (purpose: string) => void;
  testState: Record<string, BindingTestState>;
}

function TestBadge({ state }: { state?: BindingTestState }) {
  if (!state) return null;
  if (state.loading) {
    return <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" aria-label="กำลังทดสอบ" />;
  }
  const r = state.result;
  if (!r) return null;
  return r.ok ? (
    <span className="flex items-center gap-1 text-xs text-green-600">
      <CheckCircle2 className="h-3.5 w-3.5" />
      {r.latency_ms}ms
    </span>
  ) : (
    <span className="flex items-center gap-1 text-xs text-destructive max-w-[16rem] truncate" title={r.error ?? ""}>
      <XCircle className="h-3.5 w-3.5 shrink-0" />
      {r.error}
    </span>
  );
}

export function LlmBindingsList({ bindings, onEdit, onTest, testState }: Props) {
  if (bindings.length === 0) {
    return (
      <p className="text-center text-sm text-muted-foreground py-12">
        ยังไม่มีการผูก LLM กรุณาเพิ่มใหม่
      </p>
    );
  }

  const nameById = new Map(bindings.map((b) => [b.id, b.purpose]));

  return (
    <div className="space-y-2">
      {bindings.map((b) => (
        <Card key={b.id}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-foreground truncate">{b.purpose}</p>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      b.enabled
                        ? "bg-green-100 text-green-700"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {b.enabled ? "เปิดใช้งาน" : "ปิดใช้งาน"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground font-mono mt-1 truncate">
                  {b.provider_name} · {b.model}
                  {b.model_override != null ? " (แทนที่)" : ""}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  สำรอง{" "}
                  {b.fallback_binding_id != null
                    ? nameById.get(b.fallback_binding_id) ?? b.fallback_binding_id
                    : "—"}
                  {" · หมดเวลาเฉพาะการผูก "}
                  {b.timeout_override != null
                    ? `${b.timeout_override}s`
                    : "ใช้ค่าเริ่มต้นของผู้ให้บริการ"}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <TestBadge state={testState[b.purpose]} />
                <button
                  onClick={() => onTest(b.purpose)}
                  disabled={testState[b.purpose]?.loading}
                  className="rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
                >
                  ทดสอบ
                </button>
                <button
                  onClick={() => onEdit(b)}
                  className="p-1.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="แก้ไข"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
