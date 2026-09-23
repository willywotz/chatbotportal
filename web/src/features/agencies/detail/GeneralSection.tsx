import { useState } from "react";
import { toast } from "sonner";

import { AgencyLogo } from "@/shared/components/AgencyLogo";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import type { Agency } from "@/shared/types/agency";

import { isStepGeneralValid } from "../agencyForm";
import { ColorField } from "../ColorField";
import { useUpdateAgency } from "../useAgencies";

export function GeneralSection({ agency }: { agency: Agency }) {
  const updateMutation = useUpdateAgency();
  const [name, setName] = useState(agency.name);
  const [shortName, setShortName] = useState(agency.shortName);
  const [logo, setLogo] = useState(agency.logo);
  const [color, setColor] = useState(agency.color);
  const [description, setDescription] = useState(agency.description);

  const valid = isStepGeneralValid({ name, shortName });

  const save = async () => {
    try {
      await updateMutation.mutateAsync({ id: agency.id, name, shortName, logo, color, description });
      toast.success("บันทึกข้อมูลทั่วไปสำเร็จ");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    }
  };

  return (
    <div className="space-y-4 max-w-lg">
      <div className="space-y-1.5">
        <Label htmlFor="gen-name">ชื่อหน่วยงาน</Label>
        <Input id="gen-name" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="gen-short">ชื่อย่อ</Label>
        <Input id="gen-short" value={shortName} onChange={(e) => setShortName(e.target.value)} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="gen-logo">โลโก้ (emoji)</Label>
          <Input id="gen-logo" value={logo} onChange={(e) => setLogo(e.target.value)} />
        </div>
        <ColorField id="gen-color" value={color} onChange={setColor} />
      </div>
      <div className="space-y-1.5">
        <Label>ตัวอย่างโลโก้</Label>
        <div className="w-16 h-16 rounded-xl flex items-center justify-center text-3xl bg-muted">
          <AgencyLogo logo={logo} alt={name} className="w-full h-full rounded-xl" />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="gen-desc">คำอธิบาย</Label>
        <Textarea id="gen-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <Button onClick={save} disabled={updateMutation.isPending || !valid}>
        {updateMutation.isPending ? "กำลังบันทึก…" : "บันทึก"}
      </Button>
    </div>
  );
}
