import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import type { Agency } from "@/shared/types/agency";

import { DataScopeEditor } from "../DataScopeEditor";
import { parseIntOrNull } from "../agencyForm";
import { useUpdateAgency } from "../useAgencies";

export function RoutingTab({ agency }: { agency: Agency }) {
  const updateMutation = useUpdateAgency();
  const [dataScope, setDataScope] = useState<string[]>(agency.dataScope);
  const [routerHint, setRouterHint] = useState(agency.routerHint);
  const [priority, setPriority] = useState(agency.priority != null ? String(agency.priority) : "");
  const [timeoutS, setTimeoutS] = useState(
    agency.dispatchTimeoutS != null ? String(agency.dispatchTimeoutS) : "",
  );

  const save = async () => {
    try {
      await updateMutation.mutateAsync({
        id: agency.id,
        dataScope,
        routerHint,
        priority: parseIntOrNull(priority),
        dispatchTimeoutS: parseIntOrNull(timeoutS),
      });
      toast.success("บันทึก routing สำเร็จ");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    }
  };

  return (
    <div className="space-y-5 max-w-lg">
      <div className="space-y-1.5">
        <Label>ขอบเขตข้อมูล (data scope)</Label>
        <DataScopeEditor scope={dataScope} onChange={setDataScope} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="rt-hint">Router hint</Label>
        <Textarea
          id="rt-hint"
          rows={3}
          placeholder="อธิบายว่าหน่วยงานนี้ตอบคำถามแบบใด เพื่อช่วย LLM router ตัดสินใจ"
          value={routerHint}
          onChange={(e) => setRouterHint(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="rt-priority">Priority</Label>
          <Input id="rt-priority" type="number" min={1} placeholder="เช่น 1" value={priority} onChange={(e) => setPriority(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rt-timeout">Timeout (วินาที)</Label>
          <Input id="rt-timeout" type="number" min={1} placeholder="ค่าเริ่มต้นระบบ" value={timeoutS} onChange={(e) => setTimeoutS(e.target.value)} />
        </div>
      </div>
      <Button onClick={save} disabled={updateMutation.isPending}>
        {updateMutation.isPending ? "กำลังบันทึก…" : "บันทึก"}
      </Button>
    </div>
  );
}
