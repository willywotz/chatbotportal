import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import type { Agency, ApiHeader } from "@/shared/types/agency";

import { invalidHeaderIndices, isUrlValid, parseExpectedPayload, PROTOCOL_INFO } from "../agencyForm";
import { useUpdateAgency } from "../useAgencies";
import { HeadersEditor } from "../wizard/HeadersEditor";

const CONNECTION_TYPES: Agency["connectionType"][] = ["API", "MCP", "A2A"];

function sameHeaders(a: ApiHeader[], b: ApiHeader[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function ConnectionTab({ agency }: { agency: Agency }) {
  const updateMutation = useUpdateAgency();
  const [connectionType, setConnectionType] = useState<Agency["connectionType"]>(agency.connectionType);
  const [endpointUrl, setEndpointUrl] = useState(agency.endpointUrl ?? "");
  const [apiHeaders, setApiHeaders] = useState<ApiHeader[]>(agency.apiHeaders ?? []);
  const [payloadRaw, setPayloadRaw] = useState(
    agency.expectedPayload ? JSON.stringify(agency.expectedPayload, null, 2) : "",
  );
  const [mcpToolName, setMcpToolName] = useState(agency.mcpToolName ?? "");
  const [confirmOpen, setConfirmOpen] = useState(false);

  const { value: parsedPayload, error: payloadError } = parseExpectedPayload(payloadRaw);
  const urlInvalid = endpointUrl.length > 0 && !isUrlValid(endpointUrl);
  const badHeaders = invalidHeaderIndices(apiHeaders);

  const filledHeaders = apiHeaders.filter((h) => h.name && h.value);
  const identityChanged =
    connectionType !== agency.connectionType ||
    endpointUrl !== (agency.endpointUrl ?? "") ||
    !sameHeaders(filledHeaders, agency.apiHeaders ?? []) ||
    JSON.stringify(parsedPayload) !== JSON.stringify(agency.expectedPayload ?? null) ||
    mcpToolName !== (agency.mcpToolName ?? "");
  const needsConfirm =
    identityChanged && (agency.status === "active" || agency.status === "maintenance");

  const doSave = async () => {
    try {
      await updateMutation.mutateAsync({
        id: agency.id,
        connectionType,
        endpointUrl,
        apiHeaders: filledHeaders,
        expectedPayload: parsedPayload,
        mcpToolName: mcpToolName || null,
      });
      toast.success("บันทึกการเชื่อมต่อสำเร็จ");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    }
  };

  const save = () => {
    if (needsConfirm) {
      setConfirmOpen(true);
      return;
    }
    doSave();
  };

  const confirmSave = () => {
    setConfirmOpen(false);
    doSave();
  };

  return (
    <div className="space-y-5 max-w-lg">
      <div className="space-y-1.5">
        <Label>ประเภทการเชื่อมต่อ</Label>
        <div className="flex gap-2">
          {CONNECTION_TYPES.map((t) => (
            <Button
              key={t}
              type="button"
              variant={connectionType === t ? "default" : "outline"}
              size="sm"
              onClick={() => setConnectionType(t)}
            >
              {t}
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">{PROTOCOL_INFO[connectionType]}</p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="conn-endpoint">Endpoint URL</Label>
        <Input id="conn-endpoint" placeholder="https://…" value={endpointUrl} onChange={(e) => setEndpointUrl(e.target.value)} />
        {urlInvalid && <p className="text-xs text-destructive">URL ไม่ถูกต้อง</p>}
      </div>

      {connectionType === "API" && (
        <>
          <div className="space-y-1.5">
            <Label>Headers</Label>
            <HeadersEditor headers={apiHeaders} onChange={setApiHeaders} invalidIndices={badHeaders} />
            {badHeaders.length > 0 && <p className="text-xs text-destructive">กรุณากรอก Header name และ Value ให้ครบ</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="conn-payload">Expected payload (JSON template)</Label>
            <Textarea
              id="conn-payload"
              rows={5}
              placeholder='{"query": "__query__", "session_id": "__session_id__"}'
              value={payloadRaw}
              onChange={(e) => setPayloadRaw(e.target.value)}
              className="font-mono text-xs"
            />
            {payloadError && <p className="text-xs text-destructive">JSON ไม่ถูกต้อง</p>}
          </div>
        </>
      )}

      {connectionType === "MCP" && (
        <div className="space-y-1.5">
          <Label htmlFor="conn-tool">MCP tool</Label>
          <Input id="conn-tool" placeholder="เช่น chat_with_agency" value={mcpToolName} onChange={(e) => setMcpToolName(e.target.value)} className="font-mono" />
        </div>
      )}

      <Button onClick={save} disabled={updateMutation.isPending || payloadError || urlInvalid || badHeaders.length > 0 || endpointUrl.length === 0}>
        {updateMutation.isPending ? "กำลังบันทึก…" : "บันทึก"}
      </Button>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>ยืนยันการแก้ไขการเชื่อมต่อ</AlertDialogTitle>
            <AlertDialogDescription>
              การแก้ไขนี้จะทำให้หน่วยงานกลับเป็น Draft และต้องทดสอบ/เปิดใช้งานใหม่ ต้องการดำเนินการต่อหรือไม่?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>ยกเลิก</AlertDialogCancel>
            <AlertDialogAction onClick={confirmSave}>ยืนยัน</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
