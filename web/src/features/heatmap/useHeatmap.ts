import { useQuery } from '@tanstack/react-query';
import { fetchUsageHeatmap } from './heatmapApi';
import type { HeatmapRange } from './heatmapApi';
import { STALE_TIME } from '@/shared/constants/query';

export function useUsageHeatmap(range: HeatmapRange = '7d') {
  return useQuery({
    queryKey: ['usage-heatmap', range],
    queryFn: () => fetchUsageHeatmap(range),
    staleTime: STALE_TIME.slow,
  });
}
