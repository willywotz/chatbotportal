import { api } from "@/shared/lib/apiClient";

export interface LlmRoute {
  id: string;
  purpose: string;
  provider_id: string;
  provider_name: string;
  model: string;
  timeout_override: number | null;
  enabled: boolean;
}
export type LlmRouteInput = Omit<LlmRoute, "id" | "provider_name">;

export const listRoutes = () =>
  api.get<{ data: LlmRoute[]; total: number }>("/api/v1/language-model/routes");
export const createRoute = (b: LlmRouteInput) =>
  api.post<LlmRoute>("/api/v1/language-model/routes", b);
export const updateRoute = (id: string, b: Partial<LlmRouteInput>) =>
  api.patch<LlmRoute>(`/api/v1/language-model/routes/${id}`, b);
export const deleteRoute = (id: string) =>
  api.delete(`/api/v1/language-model/routes/${id}`);

export const listPurposes = () =>
  api.get<{ data: string[] }>("/api/v1/language-model/purposes");

export interface LlmRouteTestResult {
  ok: boolean;
  latency_ms: number;
  model: string | null;
  error: string | null;
}

export const testRoute = (purpose: string) =>
  api.post<LlmRouteTestResult>(`/api/v1/language-model/routes/${purpose}/test`, {});
