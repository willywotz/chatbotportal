import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";

import { DataScopeEditor } from "../DataScopeEditor";
import type { AgencyFormState } from "../agencyForm";

interface Props {
  form: AgencyFormState;
  patch: (p: Partial<AgencyFormState>) => void;
}

export function StepRouting({ form, patch }: Props) {
  return (
    <div className="space-y-5 max-w-lg">
      <div className="space-y-1.5">
        <Label>ขอบเขตข้อมูล (data scope)</Label>
        <DataScopeEditor scope={form.dataScope} onChange={(dataScope) => patch({ dataScope })} />
        <p className="text-xs text-muted-foreground">คีย์เวิร์ดที่ router ใช้พิจารณาเลือกหน่วยงานนี้</p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="wiz-hint">Router hint</Label>
        <Textarea
          id="wiz-hint"
          rows={3}
          placeholder="อธิบายว่าหน่วยงานนี้ตอบคำถามแบบใด เพื่อช่วย LLM router ตัดสินใจ"
          value={form.routerHint}
          onChange={(e) => patch({ routerHint: e.target.value })}
        />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="wiz-priority">Priority</Label>
          <Input
            id="wiz-priority"
            type="number"
            min={1}
            placeholder="เช่น 1"
            value={form.priority}
            onChange={(e) => patch({ priority: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="wiz-timeout">Timeout (วินาที)</Label>
          <Input
            id="wiz-timeout"
            type="number"
            min={1}
            placeholder="ค่าเริ่มต้นระบบ"
            value={form.dispatchTimeoutS}
            onChange={(e) => patch({ dispatchTimeoutS: e.target.value })}
          />
        </div>
      </div>
    </div>
  );
}
