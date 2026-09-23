import { useQuery } from '@tanstack/react-query';
import { fetchAgencyHealth } from './healthApi';
import { REFETCH, STALE_TIME } from '@/shared/constants/query';

export function useAgencyHealth() {
  return useQuery({
    queryKey: ['agency-health'],
    queryFn: fetchAgencyHealth,
    refetchInterval: REFETCH.fast,
    staleTime: STALE_TIME.fast,
  });
}
