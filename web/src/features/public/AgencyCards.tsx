import { AgencyLogo } from "@/shared/components/AgencyLogo";

/** Minimal card fields; satisfied by both `Agency` and `PublicAgency`. */
export interface AgencyCardItem {
  id: string;
  logo: string;
  shortName: string;
  description: string;
}

const agencyColors: Record<string, string> = {
  fda: 'border-t-[hsl(var(--gov-fda))]',
  revenue: 'border-t-[hsl(var(--gov-revenue))]',
  land: 'border-t-[hsl(var(--gov-land))]',
  dopa: 'border-t-[hsl(var(--gov-dopa))]',
};

const agencyBgColors: Record<string, string> = {
  fda: 'bg-[hsl(var(--gov-fda)/0.1)]',
  revenue: 'bg-[hsl(var(--gov-revenue)/0.1)]',
  land: 'bg-[hsl(var(--gov-land)/0.1)]',
  dopa: 'bg-[hsl(var(--gov-dopa)/0.1)]',
};

interface AgencyCardsProps {
  agencies: AgencyCardItem[];
}

export function AgencyCards({ agencies }: AgencyCardsProps) {
  return (
    <div className="flex flex-wrap justify-center gap-4 mb-12">
      {agencies.map((a, i) => (
        <div
          key={a.id}
          className={`group flex flex-col items-center gap-2 bg-card border border-border rounded-2xl p-5 w-36 transition-all duration-200 hover:scale-105 hover:shadow-lg border-t-[3px] ${agencyColors[a.id] || ''}`}
          style={{ animationDelay: `${i * 80}ms` }}
        >
          <span className={`text-3xl w-12 h-12 rounded-xl flex items-center justify-center ${agencyBgColors[a.id] || ''}`}>
            <AgencyLogo logo={a.logo} alt={a.shortName} className="w-full h-full rounded-xl" />
          </span>
          <span className="text-xs font-semibold text-foreground text-center">{a.shortName}</span>
          <span className="text-[10px] text-muted-foreground text-center leading-tight line-clamp-2">
            {a.description.slice(0, 40)}...
          </span>
        </div>
      ))}
    </div>
  );
}
