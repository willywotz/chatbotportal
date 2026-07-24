import { CheckCircle2, Loader2, Pencil, XCircle } from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import type { LlmRoute, LlmRouteTestResult } from "./llmRouteApi";

export interface RouteTestState {
  loading: boolean;
  result?: LlmRouteTestResult;
}

interface Props {
  routes: LlmRoute[];
  onEdit: (route: LlmRoute) => void;
  onTest: (purpose: string) => void;
  testState: Record<string, RouteTestState>;
}

function TestBadge({ state }: { state?: RouteTestState }) {
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

export function LlmRoutesList({ routes, onEdit, onTest, testState }: Props) {
  if (routes.length === 0) {
    return (
      <p className="text-center text-sm text-muted-foreground py-12">
        ยังไม่มีเส้นทาง LLM กรุณาเพิ่มใหม่
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {routes.map((r) => (
        <Card key={r.id}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-foreground truncate">{r.purpose}</p>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      r.enabled
                        ? "bg-green-100 text-green-700"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {r.enabled ? "เปิดใช้งาน" : "ปิดใช้งาน"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground font-mono mt-1 truncate">
                  {r.provider_name} · {r.model}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  หมดเวลาเฉพาะเส้นทาง{" "}
                  {r.timeout_override != null
                    ? `${r.timeout_override}s`
                    : "ใช้ค่าเริ่มต้นของผู้ให้บริการ"}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <TestBadge state={testState[r.purpose]} />
                <button
                  onClick={() => onTest(r.purpose)}
                  disabled={testState[r.purpose]?.loading}
                  className="rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
                >
                  ทดสอบ
                </button>
                <button
                  onClick={() => onEdit(r)}
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
