import { useQuery } from '@tanstack/react-query';
import { fetchDashboardStats, fetchAgencyUsage, fetchWeeklyTrend, fetchCategoryData, fetchLlmUsage } from '@/features/dashboard/dashboardApi';
import { REFETCH } from '@/shared/constants/query';

const REFETCH_INTERVAL = REFETCH.normal;

export function useDashboardStats() {
  return useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: fetchDashboardStats,
    refetchInterval: REFETCH_INTERVAL,
  });
}

export function useAgencyUsage() {
  return useQuery({
    queryKey: ['dashboard', 'agencyUsage'],
    queryFn: fetchAgencyUsage,
    refetchInterval: REFETCH_INTERVAL,
  });
}

export function useWeeklyTrend() {
  return useQuery({
    queryKey: ['dashboard', 'weeklyTrend'],
    queryFn: fetchWeeklyTrend,
    refetchInterval: REFETCH_INTERVAL,
  });
}

export function useCategoryData() {
  return useQuery({
    queryKey: ['dashboard', 'categoryData'],
    queryFn: fetchCategoryData,
    refetchInterval: REFETCH_INTERVAL,
  });
}

export function useLlmUsage(groupBy: string = "model") {
  return useQuery({
    queryKey: ['dashboard', 'llmUsage', groupBy],
    queryFn: () => fetchLlmUsage(groupBy),
    refetchInterval: REFETCH_INTERVAL,
  });
}
