import { api } from '@/shared/lib/apiClient';

export interface AuditEntry {
  id: string;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  object_type: string | null;
  object_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditLogResponse {
  data: AuditEntry[];
  total: number;
}

export interface AuditLogParams {
  action?: string;
  object_type?: string;
  actor?: string;
  limit?: number;
  offset?: number;
}

export async function getAuditLog(params: AuditLogParams): Promise<AuditLogResponse> {
  return api.get<AuditLogResponse>('/api/v1/audit-log/', params);
}
