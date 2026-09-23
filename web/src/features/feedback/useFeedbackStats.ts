import { useQuery } from '@tanstack/react-query';
import { fetchFeedbackStats } from '@/features/chat/feedbackApi';
import { STALE_TIME } from '@/shared/constants/query';

export function useFeedbackStats() {
  return useQuery({
    queryKey: ['feedbackStats'],
    queryFn: fetchFeedbackStats,
    staleTime: STALE_TIME.normal,
  });
}
