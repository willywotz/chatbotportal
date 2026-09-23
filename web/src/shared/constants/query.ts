/** Maximum ms of silence from the SSE server before the stream is aborted. */
export const STREAM_IDLE_TIMEOUT_MS = 30_000;

/** Polling intervals (ms) for React Query `refetchInterval`. */
export const REFETCH = {
  fast: 15_000,
  normal: 30_000,
  slow: 60_000,
  report: 5 * 60_000,
} as const;

/** Stale-time thresholds (ms) for React Query `staleTime`. */
export const STALE_TIME = {
  fast: 10_000,
  normal: 30_000,
  slow: 60_000,
  report: 5 * 60_000,
} as const;

/** Items-per-page for each paginated feature. */
export const PAGE_SIZE = {
  history: 10,
  connectionLogs: 20,
  audit: 50,
} as const;
