import { api } from '@/shared/lib/apiClient';

export interface UsageRow {
  key: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

export interface UsageParams {
  group_by: 'purpose' | 'model' | 'user';
  from?: string;
  to?: string;
}

export async function getUsage(params: UsageParams): Promise<UsageRow[]> {
  return api.get<UsageRow[]>('/api/v1/insight/usage', params);
}
