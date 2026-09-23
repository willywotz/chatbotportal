import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/apiClient";
import { STALE_TIME } from "@/shared/constants/query";

/** Display-safe agency shape returned by the anonymous `/public/agencies` endpoint. */
export interface PublicAgency {
  id: string;
  name: string;
  shortName: string;
  logo: string;
  description: string;
  connectionType: "MCP" | "API" | "A2A";
  status: string;
}

interface PublicAgencyRow {
  id: string;
  name: string;
  short_name: string | null;
  logo: string | null;
  description: string | null;
  connection_type: "MCP" | "API" | "A2A";
  status: string;
}

function mapRow(r: PublicAgencyRow): PublicAgency {
  return {
    id: r.id,
    name: r.name,
    shortName: r.short_name ?? r.name,
    logo: r.logo ?? "🏛️",
    description: r.description ?? "",
    connectionType: r.connection_type,
    status: r.status,
  };
}

export const fetchPublicAgencies = async (): Promise<PublicAgency[]> =>
  (await api.get<PublicAgencyRow[]>("/api/v1/public/agencies")).map(mapRow);

export function usePublicAgencies() {
  return useQuery({
    queryKey: ["public-agencies"],
    queryFn: fetchPublicAgencies,
    staleTime: STALE_TIME.slow,
  });
}
