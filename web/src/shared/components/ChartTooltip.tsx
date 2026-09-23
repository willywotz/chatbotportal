import type { TooltipProps } from "recharts";
import type { ValueType, NameType } from "recharts/types/component/DefaultTooltipContent";

interface ChartTooltipProps extends TooltipProps<ValueType, NameType> {
  /** Optional suffix rendered after a single value (e.g. " คำถาม"). When set, only payload[0] is shown. */
  valueSuffix?: string;
}

export function ChartTooltip({ active, payload, label, valueSuffix }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;

  if (valueSuffix !== undefined) {
    return (
      <div className="rounded-lg border bg-card px-3 py-2 shadow-lg">
        <p className="text-[10px] text-muted-foreground">{label}</p>
        <p className="text-xs font-semibold text-foreground">
          {payload[0].value}{valueSuffix}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card px-3 py-2 shadow-lg">
      <p className="text-xs font-medium text-foreground">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="text-xs text-muted-foreground">
          {p.name}: <span className="font-semibold text-foreground">{p.value?.toLocaleString()}</span>
        </p>
      ))}
    </div>
  );
}
