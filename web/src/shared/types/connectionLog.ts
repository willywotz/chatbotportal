export interface ConnectionLog {
  id: string;
  agency_id: string;
  action: string;
  connection_type: string;
  status: string;
  latency_ms: number;
  detail: string;
  created_at: string;
}