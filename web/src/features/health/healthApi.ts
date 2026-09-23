import { api } from "@/shared/lib/apiClient";

export interface AgencyHealthData {
  agencies: {
    id: string; name: string; shortName: string;
    status: 'healthy' | 'degraded' | 'down';
    uptime: number; currentLatency: number; avgLatency: number;
    errorRate: number; requestsPerMin: number; lastCheckedAt: string;
  }[];
  historical: Array<Record<string, string | number>>;
  incidents: {
    agency: string; type: string; severity: 'info' | 'warning' | 'critical';
    message: string; occurredAt: string; resolvedAt: string;
  }[];
  slaCompliance: { agency: string; uptime: number; target: number; met: boolean }[];
  generatedAt: string;
}

export function fetchAgencyHealth(): Promise<AgencyHealthData> {
  return api.get<AgencyHealthData>('/api/v1/agency-health');
}
