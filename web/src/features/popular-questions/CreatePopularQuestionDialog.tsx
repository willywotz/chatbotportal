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
import type { PopularQuestionAdmin, PopularQuestionInput } from "./popularQuestionsApi";

/** Sentinel Select value for "no agency" — Radix Select rejects an empty string value. */
const NO_AGENCY = "__none__";

interface Props {
  open: boolean;
  agencies: Agency[];
  agenciesLoading: boolean;
  mutation: UseMutationResult<PopularQuestionAdmin, Error, PopularQuestionInput>;
  onClose: () => void;
}

const initialForm = { text: "", agencyId: NO_AGENCY };

export function CreatePopularQuestionDialog({ open, agencies, agenciesLoading, mutation, onClose }: Props) {
  const [form, setForm] = useState(initialForm);

  useEffect(() => {
    if (open) setForm(initialForm);
  }, [open]);

  const canSubmit = form.text.trim() !== "";

  const handleSubmit = () => {
    mutation.mutate({
      text: form.text.trim(),
      agency_id: form.agencyId === NO_AGENCY ? null : form.agencyId,
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>เพิ่มคำถามยอดนิยม</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-2">
            <Label htmlFor="create-pq-text">คำถาม</Label>
            <Input
              id="create-pq-text"
              value={form.text}
              onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="create-pq-agency">หน่วยงาน</Label>
            <Select
              value={form.agencyId}
              onValueChange={(v) => setForm((f) => ({ ...f, agencyId: v }))}
            >
              <SelectTrigger id="create-pq-agency">
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
            สร้าง
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
