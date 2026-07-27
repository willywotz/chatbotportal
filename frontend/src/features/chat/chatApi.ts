import { api, tokenStorage } from '@/shared/lib/apiClient';
import { STREAM_IDLE_TIMEOUT_MS } from '@/shared/constants/query';
import type { AgentStep } from '@/shared/types';
import type {
  StepEvent, AgenciesEvent, IntentEvent, RoutingEvent,
  AgencyStartEvent, AgencyRespondedEvent, AgencyVerifiedEvent,
  AnswerEvent, DoneEvent, ErrorEvent,
} from '@/shared/types/chat';

export interface ChatApiRequest {
  query: string;
  conversation_id?: string;
}

export interface ChatReference {
  number?: number;
  agency_id?: string;
  agency_name?: string;
  agency?: string;
  title?: string;
  url: string | null;
}

export interface ChatApiResponse {
  success: boolean;
  data: {
    message_id: string;
    cached: boolean;
    agentSteps: AgentStep[];
    answer?: string;
    summary?: string;
    references?: ChatReference[];
    sections?: unknown[];
    errors?: unknown[];
    debug?: unknown;
  };
  conversation_id: string;
  responseTime: number;
}

export async function sendChatQuery(request: ChatApiRequest): Promise<ChatApiResponse> {
  return api.post<ChatApiResponse>('/api/v1/chat', request);
}

// --- SSE Streaming ---

export type SSEEventType = 'step' | 'agencies' | 'intent' | 'routing' | 'agency_start' | 'agency_responded' | 'agency_verified' | 'answer' | 'done' | 'error';

export interface SSECallbacks {
  onStep?: (event: StepEvent) => void;
  onAgencies?: (event: AgenciesEvent) => void;
  onIntent?: (event: IntentEvent) => void;
  onRouting?: (event: RoutingEvent) => void;
  onAgencyStart?: (event: AgencyStartEvent) => void;
  onAgencyResponded?: (event: AgencyRespondedEvent) => void;
  onAgencyVerified?: (event: AgencyVerifiedEvent) => void;
  onAnswer?: (event: AnswerEvent) => void;
  onDone?: (event: DoneEvent) => void;
  onError?: (event: ErrorEvent) => void;
}

/** Sentinel value thrown by the idle timeout race. */
const IDLE_TIMEOUT = Symbol('IDLE_TIMEOUT');

/**
 * Races reader.read() against a per-read idle deadline.
 * Returns the read result, or throws IDLE_TIMEOUT if the deadline fires first.
 * Cleans up the timer on each successful read.
 */
async function readWithIdleTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  timeoutMs: number,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const timeoutPromise = new Promise<typeof IDLE_TIMEOUT>((resolve) => {
    timer = setTimeout(() => resolve(IDLE_TIMEOUT), timeoutMs);
  });

  try {
    const result = await Promise.race([reader.read(), timeoutPromise]);
    if (result === IDLE_TIMEOUT) throw IDLE_TIMEOUT;
    return result as ReadableStreamReadResult<Uint8Array>;
  } finally {
    if (timer !== null) clearTimeout(timer);
  }
}

/**
 * Send chat query via v4 SSE streaming endpoint.
 * Returns true if SSE was used, false if fell back to JSON.
 */
export async function sendChatQuerySSE(
  request: ChatApiRequest,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
): Promise<boolean> {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
  const url = `${baseUrl}/api/v1/chat`;
  const token = tokenStorage.get();

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ ...request, stream: true }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    // Network error — caller should fallback
    return false;
  }

  // Non-SSE response (e.g. 404, 405) — fallback
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('text/event-stream')) {
    return false;
  }

  if (!response.ok) {
    // Try to parse error JSON before falling back
    try {
      const errBody = await response.json();
      // Support new envelope {"error": {"message"}} and legacy {"detail": "..."} shapes
      const errMessage = errBody.error?.message ?? errBody.detail ?? `HTTP ${response.status}`;
      callbacks.onError?.({ message: errMessage, code: response.status });
    } catch {
      callbacks.onError?.({ message: `HTTP ${response.status}`, code: response.status });
    }
    return true; // SSE endpoint existed but request failed — don't fallback
  }

  // Parse SSE stream
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatch = (block: string) => {
    if (!block.trim()) return;
    const parsed = parseSSEBlock(block);
    if (!parsed) return;
    switch (parsed.event) {
      case 'step': callbacks.onStep?.(parsed.data as StepEvent); break;
      case 'agencies': callbacks.onAgencies?.(parsed.data as AgenciesEvent); break;
      case 'intent': callbacks.onIntent?.(parsed.data as IntentEvent); break;
      case 'routing': callbacks.onRouting?.(parsed.data as RoutingEvent); break;
      case 'agency_start': callbacks.onAgencyStart?.(parsed.data as AgencyStartEvent); break;
      case 'agency_responded': callbacks.onAgencyResponded?.(parsed.data as AgencyRespondedEvent); break;
      case 'agency_verified': callbacks.onAgencyVerified?.(parsed.data as AgencyVerifiedEvent); break;
      case 'answer': callbacks.onAnswer?.(parsed.data as AnswerEvent); break;
      case 'done': callbacks.onDone?.(parsed.data as DoneEvent); break;
      case 'error': callbacks.onError?.(parsed.data as ErrorEvent); break;
    }
  };

  let idleTimeout = false;
  try {
    while (true) {
      let done: boolean;
      let value: Uint8Array | undefined;
      try {
        ({ done, value } = await readWithIdleTimeout(reader, STREAM_IDLE_TIMEOUT_MS));
      } catch (err) {
        if (err === IDLE_TIMEOUT) {
          // Stream silent for too long — cancel the underlying stream so the
          // HTTP connection is torn down (fixes the socket/stream leak), then
          // break WITHOUT marking state.done so finalizeStreaming shows the
          // connection-lost bubble rather than the generic error bubble.
          // Fire-and-forget: cancel() may not resolve if the server is truly
          // hung, so we don't await it. releaseLock() is called in finally.
          idleTimeout = true;
          reader.cancel().catch(() => {});
          break;
        }
        throw err;
      }
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop()!; // last incomplete chunk stays in buffer
      for (const part of parts) dispatch(part);
    }
  } finally {
    // On idle timeout, cancel() is already in-flight (fire-and-forget) and will
    // release the lock asynchronously — skip releaseLock() to avoid a TypeError
    // from calling it while a read() is still pending.
    // On all other paths (normal completion or thrown error), releaseLock() is safe.
    if (!idleTimeout) {
      reader.releaseLock();
      // Flush any event not terminated with \n\n
      dispatch(buffer);
    }
  }

  return true;
}

function parseSSEBlock(block: string): { event: string; data: unknown } | null {
  let eventName = 'message';
  let dataLine: string | null = null;

  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLine = line.slice(5).trim();
    }
  }

  if (!dataLine) return null;

  try {
    return { event: eventName, data: JSON.parse(dataLine) };
  } catch {
    return null;
  }
}
