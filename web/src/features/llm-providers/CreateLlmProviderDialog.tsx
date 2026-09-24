import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { PasswordInput } from "@/shared/components/ui/password-input";
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
import { HeadersEditor } from "@/features/agencies/HeadersEditor";
import { listKinds, type LlmHeader, type LlmProvider, type LlmProviderInput } from "./llmProviderApi";

function numOr(v: string, d: number): number {
  const n = Number(v);
  return v.trim() === "" || Number.isNaN(n) ? d : n;
}

interface Props {
  open: boolean;
  mutation: UseMutationResult<LlmProvider, Error, LlmProviderInput>;
  onClose: () => void;
}

const initialForm = {
  name: "",
  provider: "openai",
  model: "",
  base_url: "",
  api_key: "",
  headers: [] as LlmHeader[],
  timeout_seconds: "60",
  max_retries: "2",
  rate_limit_rps: "",
  rate_limit_rpm: "",
  max_queue_size: "50",
  enabled: true,
};

export function CreateLlmProviderDialog({ open, mutation, onClose }: Props) {
  const [form, setForm] = useState(initialForm);

  const { data: kindsData } = useQuery({ queryKey: ["llm-kinds"], queryFn: listKinds });
  const kinds = kindsData?.data ?? [];

  useEffect(() => {
    if (open) setForm(initialForm);
  }, [open]);

  const canSubmit = form.name.trim() !== "" && form.provider.trim() !== "" && form.model.trim() !== "";

  const handleSubmit = () => {
    mutation.mutate({
      name: form.name.trim(),
      provider: form.provider,
      model: form.model.trim(),
      base_url: form.base_url.trim() === "" ? null : form.base_url.trim(),
      api_key: form.api_key,
      headers: form.headers.filter((h) => h.name.trim() !== ""),
      timeout_seconds: numOr(form.timeout_seconds, 60),
      max_retries: numOr(form.max_retries, 2),
      rate_limit_rps: form.rate_limit_rps.trim() === "" ? null : Number(form.rate_limit_rps),
      rate_limit_rpm: form.rate_limit_rpm.trim() === "" ? null : Number(form.rate_limit_rpm),
      max_queue_size: numOr(form.max_queue_size, 50),
      enabled: form.enabled,
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>เพิ่มผู้ให้บริการ LLM</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-2">
            <Label htmlFor="create-name">ชื่อ</Label>
            <Input
              id="create-name"
              placeholder="เช่น OpenAI, Azure, Anthropic"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="create-kind">ชนิด (Kind)</Label>
              <Select
                value={form.provider}
                onValueChange={(v) => setForm((f) => ({ ...f, provider: v }))}
              >
                <SelectTrigger id="create-kind">
                  <SelectValue placeholder="เลือกชนิด" />
                </SelectTrigger>
                <SelectContent>
                  {kinds.map((k) => (
                    <SelectItem key={k} value={k}>
                      {k}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-model">โมเดล (Model)</Label>
              <Input
                id="create-model"
                placeholder="เช่น gpt-4o-mini"
                value={form.model}
                onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="create-base-url">Base URL (ไม่บังคับ)</Label>
            <Input
              id="create-base-url"
              placeholder="เว้นว่างเพื่อใช้ค่าเริ่มต้นของผู้ให้บริการ"
              value={form.base_url}
              onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="create-api-key">API Key</Label>
            <PasswordInput
              id="create-api-key"
              placeholder="sk-..."
              value={form.api_key}
              onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label>Headers (ไม่บังคับ)</Label>
            <HeadersEditor
              headers={form.headers}
              onChange={(headers) => setForm((f) => ({ ...f, headers }))}
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label htmlFor="create-timeout">หมดเวลา (วินาที)</Label>
              <Input
                id="create-timeout"
                type="number"
                step="any"
                min={0}
                value={form.timeout_seconds}
                onChange={(e) => setForm((f) => ({ ...f, timeout_seconds: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-max-retries">ลองใหม่สูงสุด</Label>
              <Input
                id="create-max-retries"
                type="number"
                min={0}
                value={form.max_retries}
                onChange={(e) => setForm((f) => ({ ...f, max_retries: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-max-queue">คิวสูงสุด</Label>
              <Input
                id="create-max-queue"
                type="number"
                min={0}
                value={form.max_queue_size}
                onChange={(e) => setForm((f) => ({ ...f, max_queue_size: e.target.value }))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="create-rate-rps">จำกัดอัตรา (ครั้ง/วินาที)</Label>
              <Input
                id="create-rate-rps"
                type="number"
                min={0}
                placeholder="ไม่จำกัด"
                value={form.rate_limit_rps}
                onChange={(e) => setForm((f) => ({ ...f, rate_limit_rps: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-rate-rpm">จำกัดอัตรา (ครั้ง/นาที)</Label>
              <Input
                id="create-rate-rpm"
                type="number"
                min={0}
                placeholder="ไม่จำกัด"
                value={form.rate_limit_rpm}
                onChange={(e) => setForm((f) => ({ ...f, rate_limit_rpm: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="create-enabled">เปิดใช้งาน</Label>
            <Switch
              id="create-enabled"
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
            สร้าง
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
