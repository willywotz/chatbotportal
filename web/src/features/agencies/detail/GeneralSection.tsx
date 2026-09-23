import { useRef, useState, type ChangeEvent } from "react";
import { toast } from "sonner";

import { AgencyLogo } from "@/shared/components/AgencyLogo";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import type { Agency } from "@/shared/types/agency";

import { isStepGeneralValid } from "../agencyForm";
import { ColorField } from "../ColorField";
import { useUpdateAgency, useUploadAgencyLogo } from "../useAgencies";

const ALLOWED_LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_LOGO_BYTES = 512 * 1024;

export function GeneralSection({ agency }: { agency: Agency }) {
  const updateMutation = useUpdateAgency();
  const uploadMutation = useUploadAgencyLogo();
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file after an error
    if (!file) return;
    if (!ALLOWED_LOGO_TYPES.includes(file.type)) {
      toast.error("รองรับเฉพาะไฟล์ PNG, JPEG หรือ WebP");
      return;
    }
    if (file.size > MAX_LOGO_BYTES) {
      toast.error("ขนาดไฟล์ต้องไม่เกิน 512KB");
      return;
    }
    try {
      const updated = await uploadMutation.mutateAsync({ id: agency.id, file });
      // Sync local state so the section's own save doesn't clobber the new path.
      setLogo(updated.logo);
      toast.success("อัปโหลดโลโก้สำเร็จ");
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
        <div className="flex items-center gap-3">
          <div className="w-16 h-16 rounded-xl flex items-center justify-center text-3xl bg-muted">
            <AgencyLogo logo={logo} alt={name} className="w-full h-full rounded-xl" />
          </div>
          <div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadMutation.isPending}
            >
              {uploadMutation.isPending ? "กำลังอัปโหลด…" : "อัปโหลดรูป"}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={handleFileChange}
            />
            <p className="text-[10px] text-muted-foreground mt-1">PNG, JPEG หรือ WebP ไม่เกิน 512KB</p>
          </div>
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
