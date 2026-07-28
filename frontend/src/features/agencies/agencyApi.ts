import type { ChatApiResponse } from '@/features/chat/chatApi';
import { api } from '@/shared/lib/apiClient';
import type { Agency, AgencyRow } from '@/shared/types/agency';
import { mapRowToAgency } from '@/shared/types/agency';

export interface AgencyApiResponse {
  success: boolean;
  agency: string;
  agencyName: string;
  data: {
    answer: string;
    references: { title: string; url: string }[];
    confidence: number;
  };
  responseTime: number;
}

type AgencyId = 'fda' | 'revenue' | 'dopa' | 'land';

/**
 * Query a specific agency by routing to the unified /api/v1/chat endpoint
 * and requesting only that agency.
 *
 * NOTE: The FastAPI backend handles individual-agency queries the same way
 * as the combined chat — keyword detection picks the right handler.
 * If you need a dedicated per-agency endpoint in the future, add it to
 * app/routers/chat.py and update this function.
 */
export async function queryAgency(agencyId: AgencyId, query: string): Promise<AgencyApiResponse> {
  const res = await api.post<ChatApiResponse>('/api/v1/chat', { query, model: 'onechat' });

  const answer = res.data.answer ?? res.data.summary ?? '';
  const references = (res.data.references ?? []).map((r) => ({
    title: r.title ?? r.agency_name ?? '',
    url: r.url ?? '',
  }));
  const agencyName = res.data.references?.[0]?.agency_name ?? agencyId;

  return {
    success: res.success,
    agency: agencyId,
    agencyName,
    data: { answer, references, confidence: 0 },
    responseTime: res.responseTime,
  };
}
