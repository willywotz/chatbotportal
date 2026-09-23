import { useQuery } from '@tanstack/react-query';
import { getUsage, type UsageParams } from './usageApi';
import { STALE_TIME } from '@/shared/constants/query';

const KEY = 'usage-analytics';

export function useUsage(params: UsageParams) {
  return useQuery({
    queryKey: [KEY, params],
    queryFn: () => getUsage(params),
    staleTime: STALE_TIME.normal,
    placeholderData: (prev) => prev,
  });
}
