import { AgencyLogo } from "@/shared/components/AgencyLogo";
import { Badge } from "@/shared/components/ui/badge";

import type { AgencyFormState } from "../agencyForm";

interface Props {
  form: AgencyFormState;
}

function Row({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="flex justify-between gap-4 py-1.5 border-b border-border last:border-0">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className="text-xs text-right break-all">{value}</span>
    </div>
  );
}

export function StepReview({ form }: Props) {
  return (
    <div className="max-w-lg space-y-4">
      <div className="flex items-center gap-3">
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl"
          style={{ backgroundColor: `${form.color}15` }}
        >
          <AgencyLogo logo={form.logo} alt={form.name} className="w-full h-full rounded-xl" />
        </div>
        <div>
          <p className="font-medium">{form.name}</p>
          <p className="text-xs text-muted-foreground">{form.shortName}</p>
        </div>
        <Badge className="ml-auto">{form.connectionType}</Badge>
      </div>
      <div className="rounded-lg border border-border p-4">
        <Row label="Endpoint" value={form.endpointUrl} />
        <Row label="คำอธิบาย" value={form.description} />
        <Row label="MCP tool" value={form.mcpToolName} />
        <Row label="ขอบเขตข้อมูล" value={form.dataScope.join(", ")} />
        <Row label="Router hint" value={form.routerHint} />
        <Row label="Priority" value={form.priority} />
        <Row label="Timeout (s)" value={form.dispatchTimeoutS} />
      </div>
      <p className="text-xs text-muted-foreground">
        "เปิดใช้งาน" จะตั้งสถานะเป็น Active และเข้าร่วมการ routing ทันที — หรือบันทึกเป็น Draft เพื่อกลับมาแก้ไขภายหลัง
      </p>
    </div>
  );
}
