import { Search } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import type { Agency } from "@/shared/types/agency";

import { invalidHeaderIndices, isUrlValid, parseExpectedPayload, PROTOCOL_INFO, type AgencyFormState } from "../agencyForm";
import { useDiscoverMcpTools } from "../useAgencies";
import { HeadersEditor } from "./HeadersEditor";

const CONNECTION_TYPES: Agency["connectionType"][] = ["API", "MCP", "A2A"];

interface Props {
  form: AgencyFormState;
  patch: (p: Partial<AgencyFormState>) => void;
}

export function StepConnection({ form, patch }: Props) {
  const discover = useDiscoverMcpTools();
  const payloadError = parseExpectedPayload(form.expectedPayload).error;
  const urlInvalid = form.endpointUrl.length > 0 && !isUrlValid(form.endpointUrl);
  const badHeaders = invalidHeaderIndices(form.apiHeaders);

  return (
    <div className="space-y-5 max-w-lg">
      <div className="space-y-1.5">
        <Label>ประเภทการเชื่อมต่อ</Label>
        <div className="flex gap-2">
          {CONNECTION_TYPES.map((t) => (
            <Button
              key={t}
              type="button"
              variant={form.connectionType === t ? "default" : "outline"}
              size="sm"
              onClick={() => patch({ connectionType: t })}
            >
              {t}
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">{PROTOCOL_INFO[form.connectionType]}</p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="wiz-endpoint">Endpoint URL</Label>
        <Input
          id="wiz-endpoint"
          placeholder="https://…"
          value={form.endpointUrl}
          onChange={(e) => patch({ endpointUrl: e.target.value })}
        />
        {urlInvalid && <p className="text-xs text-destructive">URL ไม่ถูกต้อง</p>}
      </div>

      {form.connectionType === "API" && (
        <>
          <div className="space-y-1.5">
            <Label>Headers</Label>
            <HeadersEditor headers={form.apiHeaders} onChange={(apiHeaders) => patch({ apiHeaders })} invalidIndices={badHeaders} />
            {badHeaders.length > 0 && <p className="text-xs text-destructive">กรุณากรอก Header name และ Value ให้ครบ</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="wiz-payload">Expected payload (JSON template)</Label>
            <Textarea
              id="wiz-payload"
              rows={5}
              placeholder='{"query": "__query__", "session_id": "__session_id__"}'
              value={form.expectedPayload}
              onChange={(e) => patch({ expectedPayload: e.target.value })}
              className="font-mono text-xs"
            />
            {payloadError && <p className="text-xs text-destructive">JSON ไม่ถูกต้อง</p>}
          </div>
        </>
      )}

      {form.connectionType === "MCP" && (
        <div className="space-y-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!form.endpointUrl.trim() || discover.isPending}
            onClick={() => discover.mutate({ endpointUrl: form.endpointUrl })}
          >
            <Search className="h-3.5 w-3.5 mr-1" />
            {discover.isPending ? "กำลังค้นหา…" : "Discover tools"}
          </Button>
          {discover.isError && (
            <p className="text-xs text-destructive">
              ค้นหา tools ไม่สำเร็จ: {discover.error?.message} — ลองใหม่ได้ หรือบันทึก Draft ไว้ก่อน
            </p>
          )}
          {discover.data && (
            <div className="space-y-1">
              {discover.data.map((tool) => (
                <button
                  key={tool.name}
                  type="button"
                  onClick={() => patch({ mcpToolName: tool.name })}
                  className={`w-full text-left rounded-md border px-3 py-2 text-sm ${
                    form.mcpToolName === tool.name ? "border-primary bg-accent" : "border-border"
                  }`}
                >
                  <span className="font-mono">{tool.name}</span>
                  <span className="block text-xs text-muted-foreground">{tool.description}</span>
                </button>
              ))}
            </div>
          )}
          {form.mcpToolName && !discover.data && (
            <p className="text-xs text-muted-foreground">
              Tool ที่เลือกไว้: <span className="font-mono">{form.mcpToolName}</span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
