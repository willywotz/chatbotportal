import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/apiClient";
import { STALE_TIME } from "@/shared/constants/query";

export interface PopularQuestionAgency {
  id: string;
  name: string;
  logo: string | null;
}

export interface PopularQuestion {
  id: string;
  text: string;
  agency: PopularQuestionAgency | null;
}

export type PopularQuestionSource = "seed" | "auto" | "manual";

export interface PopularQuestionAdmin extends PopularQuestion {
  source: PopularQuestionSource;
  pinned: boolean;
  hidden: boolean;
  sort_order: number;
  score: number | null;
}

export interface PopularQuestionInput {
  text: string;
  agency_id?: string | null;
}

export type PopularQuestionUpdate = Partial<{
  text: string;
  agency_id: string | null;
  pinned: boolean;
  hidden: boolean;
  sort_order: number;
}>;

// Both list endpoints share the `{ data: [...] }` envelope — unwrap once, here,
// so any future change to the envelope shape only needs to happen in one place.
function unwrapList<T>(res: { data: T[] }): T[] {
  return res.data;
}

export const fetchPublicPopularQuestions = async (): Promise<PopularQuestion[]> =>
  unwrapList(await api.get<{ data: PopularQuestion[] }>("/api/v1/public/popular-questions"));

export function usePublicPopularQuestions() {
  return useQuery({
    queryKey: ["public-popular-questions"],
    queryFn: fetchPublicPopularQuestions,
    staleTime: STALE_TIME.slow,
  });
}

export const listPopularQuestions = async (): Promise<PopularQuestionAdmin[]> =>
  unwrapList(
    await api.get<{ data: PopularQuestionAdmin[]; total: number }>("/api/v1/popular-questions"),
  );

export const createPopularQuestion = (body: PopularQuestionInput) =>
  api.post<PopularQuestionAdmin>("/api/v1/popular-questions", body);

export const updatePopularQuestion = (id: string, body: PopularQuestionUpdate) =>
  api.patch<PopularQuestionAdmin>(`/api/v1/popular-questions/${id}`, body);

export const deletePopularQuestion = (id: string) =>
  api.delete(`/api/v1/popular-questions/${id}`);

export const regeneratePopularQuestions = () =>
  api.post<{ status: string }>("/api/v1/popular-questions/regenerate");
