import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
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
import type { LlmBinding, LlmBindingInput } from "./llmBindingApi";
import type { LlmProvider } from "@/features/llm-providers/llmProviderApi";

// Radix Select forbids an empty-string item value; this sentinel stands in
// for "no fallback" and maps back to null in the payload.
const NO_FALLBACK = "__none__";

// Empty input means "no override" (null); otherwise coerce to a number,
// guarding against NaN. Do NOT use `Number(x) || default` — that would
// incorrectly discard an explicit, legitimate `0`.
function parseTimeoutOverride(v: string): number | null {
  const t = v.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isNaN(n) ? null : n;
}

interface Props {
  target: LlmBinding | null;
  bindings: LlmBinding[];
  providers: LlmProvider[];
  providersLoading: boolean;
  mutation: UseMutationResult<
    LlmBinding,
    Error,
    { id: string; body: Partial<LlmBindingInput> }
  >;
  onClose: () => void;
}

// `purpose` is immutable once a binding exists — it is displayed read-only
// here and never included in the update payload.
function emptyForm(target: LlmBinding | null) {
  return {
    provider_id: target?.provider_id ?? "",
    model_override: target?.model_override ?? "",
    fallback_binding_id: target?.fallback_binding_id ?? NO_FALLBACK,
    timeout_override:
      target?.timeout_override != null ? String(target.timeout_override) : "",
    enabled: target?.enabled ?? true,
  };
}

export function EditLlmBindingDialog({
  target,
  bindings,
  providers,
  providersLoading,
  mutation,
  onClose,
}: Props) {
  const [form, setForm] = useState(emptyForm(target));

  useEffect(() => {
    if (target) setForm(emptyForm(target));
  }, [target]);

  const canSubmit = form.provider_id !== "";
  const fallbackOptions = bindings.filter((b) => b.id !== target?.id);

  const handleSubmit = () => {
    if (!target) return;
    mutation.mutate({
      id: target.id,
      body: {
        provider_id: form.provider_id,
        model_override: form.model_override.trim() === "" ? null : form.model_override.trim(),
        fallback_binding_id:
          form.fallback_binding_id === NO_FALLBACK ? null : form.fallback_binding_id,
        timeout_override: parseTimeoutOverride(form.timeout_override),
        enabled: form.enabled,
      },
    });
  };

  return (
    <Dialog open={!!target} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>แก้ไขการผูก LLM</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-2">
            <Label htmlFor="edit-purpose">วัตถุประสงค์ (Purpose)</Label>
            <Input id="edit-purpose" value={target?.purpose ?? ""} disabled readOnly />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-provider">ผู้ให้บริการ (Provider)</Label>
            <Select
              value={form.provider_id}
              onValueChange={(v) => setForm((f) => ({ ...f, provider_id: v }))}
            >
              <SelectTrigger id="edit-provider">
                <SelectValue
                  placeholder={providersLoading ? "กำลังโหลด..." : "เลือกผู้ให้บริการ"}
                />
              </SelectTrigger>
              <SelectContent>
                {providers.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-model-override">โมเดลแทนที่ (Model override)</Label>
            <Input
              id="edit-model-override"
              placeholder="เว้นว่างเพื่อใช้โมเดลของผู้ให้บริการ"
              value={form.model_override}
              onChange={(e) => setForm((f) => ({ ...f, model_override: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-fallback">การผูกสำรอง (Fallback)</Label>
            <Select
              value={form.fallback_binding_id}
              onValueChange={(v) => setForm((f) => ({ ...f, fallback_binding_id: v }))}
            >
              <SelectTrigger id="edit-fallback">
                <SelectValue placeholder="ไม่มี" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_FALLBACK}>ไม่มี</SelectItem>
                {fallbackOptions.map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    {b.purpose}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-timeout-override">หมดเวลาเฉพาะการผูก (วินาที)</Label>
            <Input
              id="edit-timeout-override"
              type="number"
              step="any"
              placeholder="ใช้ค่าเริ่มต้นของผู้ให้บริการ"
              value={form.timeout_override}
              onChange={(e) => setForm((f) => ({ ...f, timeout_override: e.target.value }))}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="edit-enabled">เปิดใช้งาน</Label>
            <Switch
              id="edit-enabled"
              checked={form.enabled}
              onCheckedChange={(v) => setForm((f) => ({ ...f, enabled: v }))}
            />
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
