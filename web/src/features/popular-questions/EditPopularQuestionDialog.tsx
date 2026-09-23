import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import type { UseMutationResult } from "@tanstack/react-query";
import type { Agency } from "@/shared/types";
import type { PopularQuestionAdmin, PopularQuestionUpdate } from "./popularQuestionsApi";

/** Sentinel Select value for "no agency" — Radix Select rejects an empty string value. */
const NO_AGENCY = "__none__";

interface Props {
  target: PopularQuestionAdmin | null;
  agencies: Agency[];
  agenciesLoading: boolean;
  mutation: UseMutationResult<PopularQuestionAdmin, Error, { id: string; body: PopularQuestionUpdate }>;
  onClose: () => void;
}

function emptyForm(target: PopularQuestionAdmin | null) {
  return { text: target?.text ?? "", agencyId: target?.agency?.id ?? NO_AGENCY };
}

export function EditPopularQuestionDialog({ target, agencies, agenciesLoading, mutation, onClose }: Props) {
  const [form, setForm] = useState(emptyForm(target));

  useEffect(() => {
    if (target) setForm(emptyForm(target));
  }, [target]);

  const canSubmit = form.text.trim() !== "";

  const handleSubmit = () => {
    if (!target) return;
    mutation.mutate({
      id: target.id,
      body: {
        text: form.text.trim(),
        agency_id: form.agencyId === NO_AGENCY ? null : form.agencyId,
      },
    });
  };

  return (
    <Dialog open={!!target} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>แก้ไขคำถามยอดนิยม</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-2">
            <Label htmlFor="edit-pq-text">คำถาม</Label>
            <Input
              id="edit-pq-text"
              value={form.text}
              onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-pq-agency">หน่วยงาน</Label>
            <Select
              value={form.agencyId}
              onValueChange={(v) => setForm((f) => ({ ...f, agencyId: v }))}
            >
              <SelectTrigger id="edit-pq-agency">
                <SelectValue placeholder={agenciesLoading ? "กำลังโหลด..." : "เลือกหน่วยงาน"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_AGENCY}>ไม่ระบุ</SelectItem>
                {agencies.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            ยกเลิก
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || mutation.isPending}>
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
            บันทึก
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
