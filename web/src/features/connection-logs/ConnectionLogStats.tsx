import type { ConnectionLogInfo } from "./useConnectionLogs";

interface Props { logInfo: ConnectionLogInfo | undefined }

export function ConnectionLogStats({ logInfo }: Props) {
  const items = [
    { label: "ทั้งหมด", value: logInfo?.total_connections ?? 0, color: "text-foreground" },
    { label: "สำเร็จ", value: logInfo?.successful_connections ?? 0, color: "text-green-600 dark:text-green-400" },
    { label: "ล้มเหลว", value: logInfo?.failed_connections ?? 0, color: "text-destructive" },
    { label: "Latency เฉลี่ย (24 ชม.)", value: `${logInfo?.average_latency_ms ?? 0} ms`, color: "text-foreground" },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {items.map((s) => (
        <div key={s.label} className="border rounded-lg p-3 bg-card">
          <p className="text-xs text-muted-foreground">{s.label}</p>
          <p className={`text-xl font-semibold ${s.color}`}>{s.value}</p>
        </div>
      ))}
    </div>
  );
}
