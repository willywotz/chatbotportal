import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { PasswordInput } from "@/shared/components/ui/password-input";
import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import type { UseMutationResult } from "@tanstack/react-query";
import type { LlmProvider, LlmProviderInput } from "./llmProviderApi";

function numOr(v: string, d: number): number {
  const n = Number(v);
  return v.trim() === "" || Number.isNaN(n) ? d : n;
}

interface Props {
  target: LlmProvider | null;
  mutation: UseMutationResult<
    LlmProvider,
    Error,
    { id: string; body: Partial<LlmProviderInput> }
  >;
  onClose: () => void;
}

// The backend always returns this mask for api_key; sending it back (or
// omitting the field) leaves the stored secret untouched.
const MASKED_KEY = "*****";

function emptyForm(target: LlmProvider | null) {
  return {
    name: target?.name ?? "",
    base_url: target?.base_url ?? "",
    api_key: "",
    auth_header: target?.auth_header ?? "Authorization",
    auth_scheme: target?.auth_scheme ?? "Bearer",
    timeout_seconds: String(target?.timeout_seconds ?? 60),
    request_usage: target?.request_usage ?? false,
    rate_limit_rps: target?.rate_limit_rps != null ? String(target.rate_limit_rps) : "",
    rate_limit_rpm: target?.rate_limit_rpm != null ? String(target.rate_limit_rpm) : "",
    max_queue_size: String(target?.max_queue_size ?? 50),
    enabled: target?.enabled ?? true,
  };
}

export function EditLlmProviderDialog({ target, mutation, onClose }: Props) {
  const [form, setForm] = useState(emptyForm(target));

  useEffect(() => {
    if (target) setForm(emptyForm(target));
  }, [target]);

  const canSubmit = form.name.trim() !== "" && form.base_url.trim() !== "";

  const handleSubmit = () => {
    if (!target) return;
    const apiKey = form.api_key.trim();
    mutation.mutate({
      id: target.id,
      body: {
        name: form.name.trim(),
        base_url: form.base_url.trim(),
        ...(apiKey !== "" && apiKey !== MASKED_KEY ? { api_key: apiKey } : {}),
        auth_header: form.auth_header.trim() || "Authorization",
        auth_scheme: form.auth_scheme.trim() || "Bearer",
        timeout_seconds: numOr(form.timeout_seconds, 60),
        request_usage: form.request_usage,
        rate_limit_rps: form.rate_limit_rps.trim() === "" ? null : Number(form.rate_limit_rps),
        rate_limit_rpm: form.rate_limit_rpm.trim() === "" ? null : Number(form.rate_limit_rpm),
        max_queue_size: numOr(form.max_queue_size, 50),
        enabled: form.enabled,
      },
    });
  };

  return (
    <Dialog open={!!target} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>แก้ไขผู้ให้บริการ LLM</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-2">
            <Label htmlFor="edit-name">ชื่อ</Label>
            <Input
              id="edit-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-base-url">Base URL</Label>
            <Input
              id="edit-base-url"
              value={form.base_url}
              onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-api-key">API Key</Label>
            <PasswordInput
              id="edit-api-key"
              placeholder="เว้นว่างไว้เพื่อไม่เปลี่ยนคีย์เดิม"
              value={form.api_key}
              onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="edit-auth-header">Auth Header</Label>
              <Input
                id="edit-auth-header"
                value={form.auth_header}
                onChange={(e) => setForm((f) => ({ ...f, auth_header: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-auth-scheme">Auth Scheme</Label>
              <Input
                id="edit-auth-scheme"
                value={form.auth_scheme}
                onChange={(e) => setForm((f) => ({ ...f, auth_scheme: e.target.value }))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="edit-timeout">หมดเวลา (วินาที)</Label>
              <Input
                id="edit-timeout"
                type="number"
                step="any"
                min={0}
                value={form.timeout_seconds}
                onChange={(e) => setForm((f) => ({ ...f, timeout_seconds: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-max-queue">คิวสูงสุด</Label>
              <Input
                id="edit-max-queue"
                type="number"
                min={0}
                value={form.max_queue_size}
                onChange={(e) => setForm((f) => ({ ...f, max_queue_size: e.target.value }))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="edit-rate-rps">จำกัดอัตรา (ครั้ง/วินาที)</Label>
              <Input
                id="edit-rate-rps"
                type="number"
                min={0}
                placeholder="ไม่จำกัด"
                value={form.rate_limit_rps}
                onChange={(e) => setForm((f) => ({ ...f, rate_limit_rps: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-rate-rpm">จำกัดอัตรา (ครั้ง/นาที)</Label>
              <Input
                id="edit-rate-rpm"
                type="number"
                min={0}
                placeholder="ไม่จำกัด"
                value={form.rate_limit_rpm}
                onChange={(e) => setForm((f) => ({ ...f, rate_limit_rpm: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="edit-request-usage">บันทึกการใช้งาน (usage)</Label>
            <Switch
              id="edit-request-usage"
              checked={form.request_usage}
              onCheckedChange={(v) => setForm((f) => ({ ...f, request_usage: v }))}
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
