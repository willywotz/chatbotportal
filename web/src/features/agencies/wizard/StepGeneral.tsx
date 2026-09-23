import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";

import type { AgencyFormState } from "../agencyForm";
import { ColorField } from "../ColorField";

interface Props {
  form: AgencyFormState;
  patch: (p: Partial<AgencyFormState>) => void;
}

export function StepGeneral({ form, patch }: Props) {
  return (
    <div className="space-y-4 max-w-lg">
      <div className="space-y-1.5">
        <Label htmlFor="wiz-name">ชื่อหน่วยงาน</Label>
        <Input id="wiz-name" value={form.name} onChange={(e) => patch({ name: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="wiz-short">ชื่อย่อ</Label>
        <Input id="wiz-short" value={form.shortName} onChange={(e) => patch({ shortName: e.target.value })} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="wiz-logo">โลโก้ (emoji)</Label>
          <Input id="wiz-logo" value={form.logo} onChange={(e) => patch({ logo: e.target.value })} />
        </div>
        <ColorField id="wiz-color" value={form.color} onChange={(hex) => patch({ color: hex })} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="wiz-desc">คำอธิบาย</Label>
        <Textarea id="wiz-desc" rows={3} value={form.description} onChange={(e) => patch({ description: e.target.value })} />
      </div>
    </div>
  );
}
