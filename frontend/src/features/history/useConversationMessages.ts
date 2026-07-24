import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/lib/apiClient';
import type { ConversationMessage } from '@/shared/types/conversation';
import { STALE_TIME } from '@/shared/constants/query';

async function fetchConversationMessages(conversationId: string): Promise<ConversationMessage[]> {
  const data = await api.get<ConversationMessage[]>(
    `/api/v1/history/${conversationId}/messages`
  );
  return data ?? [];
}

export function useConversationMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ['conversationMessages', conversationId],
    queryFn: () => fetchConversationMessages(conversationId!),
    enabled: !!conversationId,
    staleTime: STALE_TIME.slow,
  });
}
