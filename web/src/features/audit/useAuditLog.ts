import { useQuery } from '@tanstack/react-query';
import { getAuditLog, type AuditLogParams } from './auditApi';
import { STALE_TIME } from '@/shared/constants/query';

const KEY = 'audit-log';

export function useAuditLog(params: AuditLogParams) {
  return useQuery({
    queryKey: [KEY, params],
    queryFn: () => getAuditLog(params),
    staleTime: STALE_TIME.normal,
    placeholderData: (prev) => prev,
  });
}
