import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchExecutiveSummary, regenerateExecutiveSummary } from '@/features/executive/executiveApi';
import { REFETCH, STALE_TIME } from '@/shared/constants/query';

export function useExecutiveSummary() {
  return useQuery({
    queryKey: ['executive', 'summary'],
    queryFn: fetchExecutiveSummary,
    staleTime: STALE_TIME.report,
    refetchInterval: REFETCH.report,
  });
}

export function useRegenerateExecutiveSummary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: regenerateExecutiveSummary,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['executive', 'summary'] }),
  });
}
