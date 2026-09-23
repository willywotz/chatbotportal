import { useQuery } from '@tanstack/react-query';
import { fetchChatHistory, type FetchChatHistoryParams } from '@/features/history/historyApi';
import { STALE_TIME } from '@/shared/constants/query';

export function useChatHistory(params: FetchChatHistoryParams = {}) {
  return useQuery({
    queryKey: ['chatHistory', params.search, params.filterAgency, params.dateFrom, params.dateTo, params.page, params.pageSize],
    queryFn: () => fetchChatHistory(params),
    staleTime: STALE_TIME.normal,
  });
}
