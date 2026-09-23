import { useConnectionLogs } from "@/features/connection-logs/useConnectionLogs";

import { AgencyConnectionLogsTab } from "../AgencyConnectionLogsTab";

export function LogsTab({ agencyId }: { agencyId: string }) {
  const { data: logs, isLoading } = useConnectionLogs({ agencyId });
  return <AgencyConnectionLogsTab logs={logs} logsLoading={isLoading} />;
}
