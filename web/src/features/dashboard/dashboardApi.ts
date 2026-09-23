import { api } from '@/shared/lib/apiClient';
import type {
  AgencyUsageDatum,
  CategoryDatum,
  DashboardStats,
  WeeklyTrendDatum,
} from '@/shared/types/dashboard';

export interface LlmUsageRow {
  key: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

interface DashboardApiResponse {
  success: boolean;
  data: {
    stats: DashboardStats;
    agencyUsage: AgencyUsageDatum[];
    weeklyTrend: WeeklyTrendDatum[];
    categoryData: CategoryDatum[];
  };
  responseTime: number;
}

async function fetchFromApi(): Promise<DashboardApiResponse> {
  return api.get<DashboardApiResponse>('/api/v1/dashboard/statistics')
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const res = await fetchFromApi();
  return res.data.stats;
}

export async function fetchAgencyUsage(): Promise<AgencyUsageDatum[]> {
  const res = await fetchFromApi();
  return res.data.agencyUsage;
}

export async function fetchWeeklyTrend(): Promise<WeeklyTrendDatum[]> {
  const res = await fetchFromApi();
  return res.data.weeklyTrend;
}

export async function fetchCategoryData(): Promise<CategoryDatum[]> {
  const res = await fetchFromApi();
  return res.data.categoryData;
}

export async function fetchLlmUsage(groupBy: string = "model"): Promise<LlmUsageRow[]> {
  try {
    return await api.get<LlmUsageRow[]>(`/api/v1/insight/usage?group_by=${groupBy}`);
  } catch {
    return [];
  }
}
