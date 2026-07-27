import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, axiosInstance } from '@/shared/lib/apiClient';
import { REFETCH, STALE_TIME } from '@/shared/constants/query';
import type { Agency } from '@/shared/types';
import type {
  AgencyLifecycleStatus,
  AgencyRow,
  ConformanceReport,
  HealthHistoryBucket,
  HealthHistoryBucketRow,
  HealthWindow,
  McpTool,
} from '@/shared/types/agency';
import { mapBucketRow, mapRowToAgency } from '@/shared/types/agency';
import type { TestResult } from '@/features/agencies/ConnectionTestResult';

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

const emptyAgencies: Agency[] = [];

async function fetchAgencies(): Promise<Agency[]> {
  try {
    const res = await api.get<{ data: AgencyRow[]; total: number }>('/api/v1/agencies');
    if (!res.data || res.data.length === 0) return emptyAgencies;
    return res.data.map(mapRowToAgency);
  } catch (err) {
    console.warn('Failed to fetch agencies from backend, using fallback', err);
    return emptyAgencies;
  }
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useAgencies() {
  return useQuery({
    queryKey: ['agencies'],
    queryFn: fetchAgencies,
    staleTime: STALE_TIME.normal,
    refetchInterval: REFETCH.slow,   // poll every 60 s (replaces Supabase realtime)
  });
}


export function useCreateAgency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (agency: Partial<Agency>) => {
      const row = await api.post<AgencyRow>('/api/v1/agencies', {
        name: agency.name,
        short_name: agency.shortName,
        logo: agency.logo,
        connection_type: agency.connectionType,
        status: agency.status,
        description: agency.description,
        data_scope: agency.dataScope ?? [],
        color: agency.color,
        endpoint_url: agency.endpointUrl,
        api_key_name: agency.apiKeyName,
        auth_method: agency.authMethod,
        auth_header: agency.authHeader,
        base_path: agency.basePath,
        request_format: agency.requestFormat,
        api_endpoints: agency.apiEndpoints ?? [],
        response_schema: agency.responseSchema ?? [],
        api_spec_raw: agency.apiSpecRaw,
        expected_payload: agency.expectedPayload ?? null,
        api_headers: agency.apiHeaders ?? [],
        priority: agency.priority,
        router_hint: agency.routerHint,
        dispatch_timeout_s: agency.dispatchTimeoutS,
        mcp_tool_name: agency.mcpToolName,
      });
      return mapRowToAgency(row);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agencies'] }),
  });
}

export function useUpdateAgency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (agency: Partial<Agency> & { id: string }) => {
      const row = await api.patch<AgencyRow>(`/api/v1/agencies/${agency.id}`, {
        name: agency.name,
        short_name: agency.shortName,
        logo: agency.logo,
        connection_type: agency.connectionType,
        status: agency.status,
        description: agency.description,
        data_scope: agency.dataScope,
        color: agency.color,
        endpoint_url: agency.endpointUrl,
        api_key_name: agency.apiKeyName,
        auth_method: agency.authMethod,
        auth_header: agency.authHeader,
        base_path: agency.basePath,
        request_format: agency.requestFormat,
        api_endpoints: agency.apiEndpoints,
        response_schema: agency.responseSchema,
        api_spec_raw: agency.apiSpecRaw,
        expected_payload: agency.expectedPayload,
        api_headers: agency.apiHeaders,
        priority: agency.priority,
        router_hint: agency.routerHint,
        dispatch_timeout_s: agency.dispatchTimeoutS,
        mcp_tool_name: agency.mcpToolName,
      });
      return mapRowToAgency(row);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agencies'] }),
  });
}

export function useUploadAgencyLogo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, file }: { id: string; file: File }): Promise<Agency> => {
      const formData = new FormData();
      formData.append('file', file);
      // Uses fetch (not axios) so the browser sets multipart/form-data with
      // the correct boundary itself, instead of axios's default JSON header.
      const res = await fetch(`${axiosInstance.defaults.baseURL}/api/v1/agencies/${id}/logo`, {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.error?.message ?? data?.detail ?? 'Request failed');
      }
      return mapRowToAgency(data as AgencyRow);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agencies'] }),
  });
}

export function useDeleteAgency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete(`/api/v1/agencies/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agencies'] }),
  });
}

export function useTestConnection() {
  const qc = useQueryClient();

  return useMutation<TestResult, Error, { agencyId: string }>({
    mutationFn: async ({ agencyId }) => {
      return await api.get<TestResult>(`/api/v1/agencies/${agencyId}/test`);
    },
    onSuccess: (_data, variables) => {
      // Refresh the connection-logs list for this ag ency so the log panel
      // shows the new entry without a manual reload.
      qc.invalidateQueries({ queryKey: ['connection-logs', variables.agencyId] }); // matches ['connection-logs', agencyId, ...rest]
    },
  });
}

export function useRunConformance() {
  const qc = useQueryClient();
  return useMutation<ConformanceReport, Error, { agencyId: string }>({
    mutationFn: async ({ agencyId }) =>
      await api.post<ConformanceReport>(`/api/v1/agencies/${agencyId}/conformance`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agencies'] }),
  });
}

export function useHealthHistory(agencyId: string | undefined, healthWindow: HealthWindow) {
  return useQuery({
    queryKey: ['agency-health-history', agencyId, healthWindow],
    queryFn: async (): Promise<HealthHistoryBucket[]> => {
      const res = await api.get<{ data: HealthHistoryBucketRow[] }>(
        `/api/v1/agencies/${agencyId}/health/history`,
        { window: healthWindow },
      );
      return res.data.map(mapBucketRow);
    },
    enabled: Boolean(agencyId),
  });
}

export function useUpdateAgencyStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: AgencyLifecycleStatus }) => {
      const row = await api.patch<AgencyRow>(`/api/v1/agencies/${id}/status`, { status });
      return mapRowToAgency(row);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agencies'] }),
  });
}

interface McpToolRow {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export function useDiscoverMcpTools() {
  return useMutation({
    mutationFn: async ({ endpointUrl }: { endpointUrl: string }): Promise<McpTool[]> => {
      const res = await api.post<{ tools: McpToolRow[] }>('/api/v1/agencies/mcp/discover', {
        endpoint_url: endpointUrl,
      });
      return res.tools.map((t) => ({
        name: t.name,
        description: t.description,
        inputSchema: t.input_schema,
      }));
    },
  });
}
