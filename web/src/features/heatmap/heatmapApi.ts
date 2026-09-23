import { api } from "@/shared/lib/apiClient";

export type HeatmapRange = '7d' | '30d' | '90d';

export interface UsageHeatmapData {
  range: HeatmapRange; days: number; sampleSize: number; totalMessages: number;
  days_labels: string[]; hours: number[];
  agencies: { id: string; name: string }[];
  hourlyByAgency: { agency: string; agencyId: string; data: number[] }[];
  dayHourMatrix: { day: string; dayIndex: number; data: number[] }[];
  insights: {
    peakDay: string; peakHour: string; peakValue: number; totalRequests: number;
    businessHoursPercent: number;
    busiest: { agency: string; total: number; peakHour: number };
    recommendation: string;
  };
  generatedAt: string;
}

export function fetchUsageHeatmap(range: HeatmapRange = '7d'): Promise<UsageHeatmapData> {
  return api.get<UsageHeatmapData>(`/api/v1/usage-heatmap?range=${range}`);
}
