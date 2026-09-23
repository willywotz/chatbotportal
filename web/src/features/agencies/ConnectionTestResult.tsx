import { CheckCircle2, Loader2, Circle, XCircle, AlertTriangle } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";

interface TestStep {
  step: number;
  label: string;
  status: string;  // "done" | "error"
  timeMs: number;
}

interface AgentCardInfo {
  name: string;
  skills: string[];
  capabilities?: Record<string, unknown>;
}

export interface TestResult {
  success: boolean;
  protocol?: string;
  version?: string;
  steps?: TestStep[];
  latency?: string;
  error?: string;

  // REST-only
  status_code?: number | null;
  status_text?: string;
  server?: string;
  content_type?: string;

  // MCP-only
  capabilities?: string[];
  server_info?: Record<string, unknown>;

  // A2A-only
  agent_card?: AgentCardInfo;
}

interface Props {
  result: TestResult | null;
  loading: boolean;
}

function StatusCodeBadge({ code }: { code: number }) {
  const variant = code >= 200 && code < 300 ? "default" : code < 400 ? "secondary" : "destructive";
  return (
    <Badge variant={variant} className="text-[10px] font-mono ml-2">
      HTTP {code}
    </Badge>
  );
}

export function ConnectionTestResult({ result, loading }: Props) {
  if (!loading && !result) return null;

  const icon = loading
    ? <Loader2 className="h-4 w-4 animate-spin text-primary" />
    : result?.success
      ? <CheckCircle2 className="h-4 w-4 text-green-500" />
      : <XCircle className="h-4 w-4 text-destructive" />;

  const title = loading
    ? "กำลังทดสอบการเชื่อมต่อ..."
    : result?.success
      ? `เชื่อมต่อสำเร็จ — ${[result?.protocol, result?.version].filter((v) => v && v !== "-").join(" ")}`
      : `เชื่อมต่อล้มเหลว — ${result?.error || 'Unknown error'}`;

  return (
    <div className={`rounded-lg border p-4 space-y-3 text-sm ${
      !loading && result && !result.success
        ? "border-destructive/30 bg-destructive/5"
        : "border-border bg-muted/30"
    }`}>
      <div className="flex items-center gap-2 font-medium text-foreground">
        {icon}
        <span className="flex-1">{title}</span>
        {result?.status_code && <StatusCodeBadge code={result.status_code} />}
      </div>

      <div className="space-y-1.5 pl-6">
        {(result?.steps || []).map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            {loading && i === (result?.steps?.length ?? 0) - 1
              ? <Loader2 className="h-3 w-3 animate-spin text-primary" />
              : s.status === 'done'
                ? <CheckCircle2 className="h-3 w-3 text-green-500" />
                : s.status === 'error'
                  ? <AlertTriangle className="h-3 w-3 text-destructive" />
                  : <Circle className="h-3 w-3 text-muted-foreground" />}
            <span className="text-foreground">{s.label}</span>
            <span className="ml-auto text-muted-foreground">{s.timeMs}ms</span>
          </div>
        ))}
      </div>

      {result && !loading && (
        <div className="pl-6 text-xs text-muted-foreground space-y-1">
          <p>Latency: <span className="font-medium text-foreground">{result.latency ?? "-"}</span></p>
          {result.status_code && (
            <p>Status: <span className="font-medium text-foreground">{result.status_code} {result.status_text}</span></p>
          )}
          {result.server && result.server !== 'unknown' && (
            <p>Server: <span className="font-medium text-foreground">{result.server}</span></p>
          )}
          {result.content_type && result.content_type !== 'unknown' && (
            <p>Content-Type: <span className="font-medium text-foreground">{result.content_type}</span></p>
          )}
          {result.capabilities && (
            <p>Capabilities: <span className="font-medium text-foreground">{result.capabilities.join(', ')}</span></p>
          )}
          {result.agent_card && (
            <p>Agent: <span className="font-medium text-foreground">{result.agent_card.name}</span>
              {result.agent_card.skills.length > 0 && (
                <> — Skills: <span className="font-medium text-foreground">{result.agent_card.skills.join(', ')}</span></>
              )}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
