export interface ApiEndpoint {
  method: string;
  path: string;
  description: string;
}

export interface ApiHeader {
  name: string;
  value: string;
}

export interface ResponseField {
  field: string;
  type: string;
  description: string;
  example?: string;
}

export const LIFECYCLE_STATUSES = ["draft", "active", "maintenance", "disabled"] as const;
export type AgencyLifecycleStatus = (typeof LIFECYCLE_STATUSES)[number];

export type HealthState = "up" | "degraded" | "down" | "unknown";

export interface AgencyHealth {
  state: HealthState;
  uptime24h: number | null;
  avgLatencyMs24h: number | null;
  lastCheckAt: string | null;
}

export const UNKNOWN_HEALTH: AgencyHealth = {
  state: "unknown",
  uptime24h: null,
  avgLatencyMs24h: null,
  lastCheckAt: null,
};

export type HealthWindow = "24h" | "7d" | "30d";

export interface HealthHistoryBucket {
  bucketStart: string;
  uptimePct: number;
  avgLatencyMs: number;
  checks: number;
  failures: number;
}

// snake_case wire shape of one history bucket
export interface HealthHistoryBucketRow {
  bucket_start: string;
  uptime_pct: number;
  avg_latency_ms: number;
  checks: number;
  failures: number;
}

export function mapBucketRow(row: HealthHistoryBucketRow): HealthHistoryBucket {
  return {
    bucketStart: row.bucket_start,
    uptimePct: row.uptime_pct,
    avgLatencyMs: row.avg_latency_ms,
    checks: row.checks,
    failures: row.failures,
  };
}

export interface McpTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export function normalizeStatus(raw: string): AgencyLifecycleStatus {
  return (LIFECYCLE_STATUSES as readonly string[]).includes(raw)
    ? (raw as AgencyLifecycleStatus)
    : "disabled";
}

export interface Agency {
  id: string;
  name: string;
  shortName: string;
  logo: string;
  connectionType: 'MCP' | 'API' | 'A2A';
  status: AgencyLifecycleStatus;
  description: string;
  dataScope: string[];
  totalCalls: number;
  color: string;
  endpointUrl: string;
  apiKeyName?: string | null;
  authMethod?: string;
  authHeader?: string;
  basePath?: string;
  requestFormat?: string;
  apiEndpoints?: ApiEndpoint[];
  responseSchema?: ResponseField[];
  apiSpecRaw?: string | null;
  expectedPayload?: Record<string, unknown> | null;
  priority: number | null;
  routerHint: string;
  dispatchTimeoutS: number | null;
  mcpToolName: string | null;
  ratingUp: number;
  ratingDown: number;
  health: AgencyHealth;
  createdAt?: string;
  updatedAt?: string;
  apiHeaders?: ApiHeader[];
}

// DB row shape (snake_case) → mapped to Agency (camelCase)
export interface AgencyRow {
  id: string;
  name: string;
  short_name: string;
  logo: string;
  connection_type: string;
  status: string;
  description: string;
  data_scope: string[];
  total_calls: number;
  color: string;
  endpoint_url: string;
  api_key_name: string | null;
  auth_method: string;
  auth_header: string;
  base_path: string;
  request_format: string;
  api_endpoints: ApiEndpoint[];
  response_schema: ResponseField[];
  api_spec_raw: string | null;
  expected_payload: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  api_headers: ApiHeader[];
  priority?: number | null;
  router_hint?: string | null;
  dispatch_timeout_s?: number | null;
  mcp_tool_name?: string | null;
  rating_up?: number;
  rating_down?: number;
  health?: {
    state: HealthState;
    uptime_24h: number | null;
    avg_latency_ms_24h: number | null;
    last_check_at: string | null;
  } | null;
}

export function mapRowToAgency(row: AgencyRow): Agency {
  return {
    id: row.id,
    name: row.name,
    shortName: row.short_name,
    logo: row.logo,
    connectionType: row.connection_type as Agency['connectionType'],
    status: normalizeStatus(row.status),
    description: row.description,
    dataScope: row.data_scope,
    totalCalls: row.total_calls,
    color: row.color,
    endpointUrl: row.endpoint_url,
    apiKeyName: row.api_key_name,
    authMethod: row.auth_method,
    authHeader: row.auth_header,
    basePath: row.base_path,
    requestFormat: row.request_format,
    apiEndpoints: row.api_endpoints,
    responseSchema: row.response_schema,
    apiSpecRaw: row.api_spec_raw,
    expectedPayload: row.expected_payload,
    priority: row.priority ?? null,
    routerHint: row.router_hint ?? "",
    dispatchTimeoutS: row.dispatch_timeout_s ?? null,
    mcpToolName: row.mcp_tool_name ?? null,
    ratingUp: row.rating_up ?? 0,
    ratingDown: row.rating_down ?? 0,
    health: row.health
      ? {
          state: row.health.state,
          uptime24h: row.health.uptime_24h,
          avgLatencyMs24h: row.health.avg_latency_ms_24h,
          lastCheckAt: row.health.last_check_at,
        }
      : UNKNOWN_HEALTH,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    apiHeaders: row.api_headers ?? [],
  };
}

export interface AgentStep {
  icon: string;
  label: string;
  detail?: string;
  status: 'pending' | 'active' | 'done';
}
