import { api } from "@/shared/lib/apiClient";

export interface LlmProvider {
  id: string;
  name: string;
  base_url: string;
  api_key: string;
  auth_header: string;
  auth_scheme: string;
  timeout_seconds: number;
  request_usage: boolean;
  rate_limit_rps: number | null;
  rate_limit_rpm: number | null;
  max_queue_size: number;
  enabled: boolean;
}
export type LlmProviderInput = Omit<LlmProvider, "id">;

export const listProviders = () =>
  api.get<{ data: LlmProvider[]; total: number }>("/api/v1/language-model/providers");
export const createProvider = (b: LlmProviderInput) =>
  api.post<LlmProvider>("/api/v1/language-model/providers", b);
export const updateProvider = (id: string, b: Partial<LlmProviderInput>) =>
  api.patch<LlmProvider>(`/api/v1/language-model/providers/${id}`, b);
export const deleteProvider = (id: string) =>
  api.delete(`/api/v1/language-model/providers/${id}`);
