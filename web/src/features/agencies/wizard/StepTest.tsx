import { CheckCircle2, ShieldCheck, XCircle } from "lucide-react";

import type { ConformanceReport } from "@/shared/types/agency";
import { Button } from "@/shared/components/ui/button";

import { useRunConformance } from "../useAgencies";

interface Props {
  agencyId: string;
  onResult?: (passed: boolean) => void;
}

function ConformanceResult({ report }: { report: ConformanceReport }) {
  return (
    <div
      className={`rounded-lg border p-4 space-y-3 text-sm ${
        report.passed ? "border-border bg-muted/30" : "border-destructive/30 bg-destructive/5"
      }`}
    >
      <div className="flex items-center gap-2 font-medium text-foreground">
        {report.passed ? (
          <CheckCircle2 className="h-4 w-4 text-green-500" />
        ) : (
          <XCircle className="h-4 w-4 text-destructive" />
        )}
        <span>{report.passed ? "ผ่านการทดสอบ Conformance" : "ยังไม่ผ่านการทดสอบ Conformance"}</span>
      </div>
      <div className="space-y-1.5 pl-6">
        {report.checks.map((c) => (
          <div key={c.name} className="flex items-center gap-2 text-xs">
            {c.passed ? (
              <CheckCircle2 className="h-3 w-3 text-green-500" />
            ) : (
              <XCircle className="h-3 w-3 text-destructive" />
            )}
            <span className="text-foreground">{c.name}</span>
            {c.detail && <span className="ml-auto text-muted-foreground">{c.detail}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function StepTest({ agencyId, onResult }: Props) {
  const mutation = useRunConformance();
  const run = () => mutation.mutate({ agencyId }, { onSuccess: (report) => onResult?.(report.passed) });

  return (
    <div className="space-y-4 max-w-lg">
      <p className="text-sm text-muted-foreground">
        รันชุดทดสอบความสอดคล้อง (conformance) กับ endpoint ที่ตั้งค่าไว้ — ต้องผ่านก่อนจึงจะเปิดใช้งานได้
        หากยังไม่ผ่านสามารถบันทึกเป็น Draft แล้วกลับมาแก้ไขภายหลังได้
      </p>
      <Button onClick={run} disabled={mutation.isPending}>
        <ShieldCheck className="h-4 w-4 mr-1.5" />
        {mutation.isPending ? "กำลังทดสอบ…" : "รันชุดทดสอบ Conformance"}
      </Button>
      {mutation.isError && (
        <p className="text-sm text-destructive">
          ทดสอบไม่สำเร็จ: {mutation.error?.message ?? "Request failed"}
        </p>
      )}
      {mutation.data && <ConformanceResult report={mutation.data} />}
    </div>
  );
}
