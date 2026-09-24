import { api } from "@/shared/lib/apiClient";

export interface LlmBinding {
  id: string;
  purpose: string;
  provider_id: string;
  provider_name: string;
  model: string;
  model_override: string | null;
  timeout_override: number | null;
  enabled: boolean;
}
export type LlmBindingInput = {
  provider_id: string;
  model_override: string | null;
  timeout_override: number | null;
  enabled: boolean;
};

export const listBindings = () =>
  api.get<{ data: LlmBinding[]; total: number }>("/api/v1/language-model/bindings");
export const updateBinding = (id: string, b: Partial<LlmBindingInput>) =>
  api.patch<LlmBinding>(`/api/v1/language-model/bindings/${id}`, b);

export const listPurposes = () =>
  api.get<{ data: string[] }>("/api/v1/language-model/purposes");

export interface LlmBindingTestResult {
  ok: boolean;
  latency_ms: number;
  model: string | null;
  error: string | null;
}

export const testBinding = (purpose: string) =>
  api.post<LlmBindingTestResult>(`/api/v1/language-model/bindings/${purpose}/test`, {});
