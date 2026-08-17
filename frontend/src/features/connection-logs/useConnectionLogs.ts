import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/lib/apiClient';
import { ConnectionLog } from '@/shared/types/connectionLog';
import { REFETCH } from '@/shared/constants/query';

export interface ConnectionLogResponse {
  search: string | null;
  page: number;
  page_size: number;
  items: ConnectionLog[];
  total_items: number;

  total_connections: number;
  successful_connections: number;
  failed_connections: number;
  average_latency_ms: number;
}

export interface ConnectionLogParams {
  page?: number;
  limit?: number;
  search?: string;
  agencyId?: string;
  status?: string;
  connectionType?: string;
  includeTest?: boolean;
}

// Query-key factory: the full key list + a partial prefix for invalidation.
// Callers that invalidate (e.g. after a connection test) use `list(agencyId)`
// so every matching list cache entry is dropped regardless of its filters.
export const connectionLogKeys = {
  list: (agencyId?: string): unknown[] => ['connection-logs', agencyId ?? null],
  listAll: (params: ConnectionLogParams = {}): unknown[] => [
    'connection-logs',
    params.agencyId ?? null,
    params.page ?? null,
    params.limit ?? null,
    params.search ?? null,
    params.status ?? null,
    params.connectionType ?? null,
    params.includeTest ?? false,
  ],
};

async function fetchConnectionLogs(params: ConnectionLogParams = {}): Promise<ConnectionLogResponse> {
  const qs = new URLSearchParams();
  if (params.page) qs.set('page', String(params.page));
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.search) qs.set('search', params.search);
  if (params.agencyId) qs.set('agency_id', params.agencyId);
  if (params.status) qs.set('status', params.status);
  if (params.connectionType) qs.set('connection_type', params.connectionType);
  if (params.includeTest) qs.set('include_test', 'true');
  const query = qs.toString();
  return await api.get<ConnectionLogResponse>(`/api/v1/connection-logs${query ? `?${query}` : ''}`);
}

export function useConnectionLogs(params: ConnectionLogParams = {}) {
  return useQuery({
    queryKey: connectionLogKeys.listAll(params),
    queryFn: () => fetchConnectionLogs(params),
    refetchInterval: REFETCH.normal,
    placeholderData: (prev) => prev,
    
    initialData: {
      search: null,
      page: 1,
      page_size: 20,
      items: [],
      total_items: 0,
      total_connections: 0,
      successful_connections: 0,
      failed_connections: 0,
      average_latency_ms: 0,
    },
  });
}

export interface ConnectionLogInfo {
  total_connections: number;
  successful_connections: number;
  failed_connections: number;
  average_latency_ms: number;
}

async function fetchConnectionLogInfo(includeTest?: boolean): Promise<ConnectionLogInfo> {
  const query = includeTest ? '?include_test=true' : '';
  return await api.get<ConnectionLogInfo>(`/api/v1/connection-logs/info${query}`);
}

export function useConnectionLogInfo(includeTest?: boolean) {
  return useQuery({
    queryKey: ['connection-log-info', includeTest ?? false],
    queryFn: () => fetchConnectionLogInfo(includeTest),
    refetchInterval: REFETCH.normal,
  });
}