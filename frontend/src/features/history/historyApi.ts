import { api } from '@/shared/lib/apiClient';
import { conversationHistory as fallback } from '@/shared/data/mockData';

export interface HistoryItem {
  id: string;
  title: string;
  preview: string;
  date: string;
  agencies: string[];
  status: 'success' | 'failed';
  messageCount?: number;
  responseTime?: string;
}

export interface HistoryApiResponse {
  success: boolean;
  data: HistoryItem[];
  total: number;
  responseTime: number;
}

export interface FetchChatHistoryParams {
  search?: string;
  filterAgency?: string;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}

export async function fetchChatHistory(
  params: FetchChatHistoryParams = {}
): Promise<HistoryApiResponse> {
  try {
    const qs = new URLSearchParams();
    if (params.search) qs.set('search', params.search);
    if (params.filterAgency) qs.set('filterAgency', params.filterAgency);
    if (params.dateFrom) qs.set('date_from', params.dateFrom);
    if (params.dateTo) qs.set('date_to', params.dateTo);
    if (params.page && params.page > 1) qs.set('page', String(params.page));
    if (params.pageSize) qs.set('page_size', String(params.pageSize));

    const query = qs.toString() ? `?${qs.toString()}` : '';
    const res = await api.get<HistoryApiResponse>(`/api/v1/history${query}`);

    if (res.success) return res;
    throw new Error('API unsuccessful');
  } catch {
    console.warn('History API failed, using fallback');
    const items = fallback as HistoryItem[];
    return { success: true, data: items, total: items.length, responseTime: 0 };
  }
}

export interface SaveConversationInput {
  title: string;
  preview: string;
  agencies: string[];
  status: 'success' | 'failed';
  responseTime?: string;
  messages: {
    id?: string;
    role: 'user' | 'assistant';
    content: string;
    agentSteps?: unknown[];
    sources?: unknown[];
    rating?: string | null;
  }[];
}

export async function saveConversation(input: SaveConversationInput): Promise<string | null> {
  try {
    const res = await api.post<{ success: boolean; conversationId: string }>('/api/v1/history', {
      title: input.title,
      preview: input.preview,
      agencies: input.agencies,
      status: input.status,
      response_time: input.responseTime,
      messages: input.messages.map((m) => ({
        id: m.id ?? undefined,
        role: m.role,
        content: m.content,
        agent_steps: m.agentSteps ?? [],
        sources: m.sources ?? [],
        rating: m.rating ?? null,
      })),
    });
    return res.conversationId ?? null;
  } catch (err) {
    console.warn('Failed to save conversation:', err);
    return null;
  }
}

export async function deleteConversation(id: string): Promise<boolean> {
  try {
    await api.delete(`/api/v1/history/${id}`);
    return true;
  } catch (err) {
    console.warn('Failed to delete conversation:', err);
    return false;
  }
}
