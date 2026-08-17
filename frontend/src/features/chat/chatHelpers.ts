import type { AgentStep, ChatMessage, StreamingState } from '@/shared/types';
import type {
  AgenciesEvent, AgencyRespondedEvent, AgencyStartEvent, AgencyVerifiedEvent,
  AgentStepsSnapshot, AnswerEvent, DoneEvent, ErrorEvent, IntentEvent, RoutingEvent, StepEvent,
} from '@/shared/types/chat';
import { generateUniqueId } from '@/shared/lib/utils';

export const INITIAL_STREAMING_STATE: StreamingState = {
  pipelineSteps: [],
  currentStep: null,
  agencies: [],
  intent: null,
  routing: null,
  agencyStatuses: {},
  answer: null,
  sections: [],
  errors: [],
  summary: null,
  summaryReferences: [],
  threadName: null,
  sessionId: null,
  messageId: null,
  totalMs: null,
  done: false,
};

export const STEP_LABELS: Record<string, { icon: string; label: string }> = {
  discover: { icon: '🔍', label: 'ค้นหาหน่วยงาน' },
  classify: { icon: '🧠', label: 'วิเคราะห์คำถาม' },
  invoke: { icon: '🔗', label: 'สืบค้นจากหน่วยงาน' },
  verify: { icon: '✅', label: 'ตรวจสอบความเกี่ยวข้อง' },
  summarize: { icon: '📌', label: 'สรุปภาพรวม' },
  synthesize: { icon: '📝', label: 'สังเคราะห์คำตอบ' },
};

export function buildAgentStepsFromStreaming(state: StreamingState): AgentStep[] {
  const steps: AgentStep[] = [];

  for (const ps of state.pipelineSteps) {
    const info = STEP_LABELS[ps.name] ?? { icon: '⚙️', label: ps.name };
    steps.push({
      icon: info.icon,
      label: info.label + (ps.ms ? ` (${(ps.ms / 1000).toFixed(1)}s)` : ''),
      status: ps.status === 'done' ? 'done' : 'active',
    });
  }

  const agencyEntries = Object.values(state.agencyStatuses);
  if (agencyEntries.length > 0) {
    for (const a of agencyEntries) {
      const statusIcon =
        a.status === 'error' ? '❌' :
        a.status === 'passed' ? '✅' :
        a.status === 'rejected' ? '⚠️' :
        a.status === 'ok' ? '⏳' : '🔗';
      steps.push({
        icon: statusIcon,
        label: a.agencyName ?? a.agencyId,
        detail: a.errorType ?? undefined,
        status: a.status === 'running' ? 'active' : 'done',
      });
    }
  }

  return steps;
}

/** Builds the persisted-shape pipeline snapshot from a completed StreamingState. */
export function buildAgentStepsSnapshot(state: StreamingState): AgentStepsSnapshot | null {
  const steps = (state.pipelineSteps ?? [])
    .filter((s) => s.status === 'done')
    .map((s) => ({ name: s.name, ms: s.ms }));
  const agencies = Object.values(state.agencyStatuses ?? {}).map((a) => ({
    id: a.agencyId,
    name: a.agencyName,
    status: a.status,
    errorType: a.errorType ?? null,
    relevanceScore: a.relevanceScore ?? null,
    sectionLabel: a.sectionLabel ?? null,
  }));
  const errors = (state.errors ?? []).map((e) => ({
    agency: e.agency, name: e.name, errorType: e.errorType, message: e.message,
  }));
  if (!steps.length && !agencies.length && !errors.length) return null;
  return { steps, agencies, errors };
}

export function formatTimestamp(): string {
  return new Date().toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Builds the assistant ChatMessage from a completed StreamingState.
 * Returns null if there is no answer and done is true (i.e. nothing to show).
 */
export function buildAiMessageFromState(state: StreamingState): ChatMessage | null {
  if (!state.answer) return null;

  return {
    id: state.messageId ?? generateUniqueId(),
    role: 'assistant',
    content: state.answer,
    timestamp: formatTimestamp(),
    agentSteps: buildAgentStepsFromStreaming(state),
    pipeline: buildAgentStepsSnapshot(state),
    sources: state.sections?.flatMap((s) =>
      s.agencies.map((a) => ({ agency: a.name, url: '', title: s.title }))
    ),
    summary: state.summary,
    summaryReferences: state.summaryReferences,
    rating: null,
  };
}

export function buildConnectionLostMessage(): ChatMessage {
  return {
    id: generateUniqueId(),
    role: 'assistant',
    content: 'ขออภัย การเชื่อมต่อถูกตัด โปรดลองอีกครั้ง',
    timestamp: formatTimestamp(),
    rating: null,
  };
}

export function buildGenericErrorMessage(): ChatMessage {
  return {
    id: generateUniqueId(),
    role: 'assistant',
    content: 'ขออภัย ฉันไม่สามารถตอบคำถามได้ในขณะนี้ โปรดลองอีกครั้งในภายหลัง',
    timestamp: formatTimestamp(),
    rating: null,
  };
}

// --- Pure streaming state reducers ---
// Each takes the previous StreamingState + an SSE event and returns the next state.
// These are free of React and I/O so they can be unit-tested directly.

export function applyStepEvent(prev: StreamingState, event: StepEvent): StreamingState {
  const steps = [...prev.pipelineSteps];
  const existingIdx = steps.findIndex((s) => s.name === event.name && s.status === 'running');
  if (event.status === 'running') {
    steps.push({ name: event.name, status: 'running', ms: null });
  } else if (existingIdx >= 0) {
    steps[existingIdx] = { name: event.name, status: 'done', ms: event.ms };
  } else {
    steps.push({ name: event.name, status: 'done', ms: event.ms });
  }
  return {
    ...prev,
    pipelineSteps: steps,
    currentStep: event.status === 'running' ? event.name : prev.currentStep,
  };
}

export function applyAgenciesEvent(prev: StreamingState, event: AgenciesEvent): StreamingState {
  return { ...prev, agencies: event.agencies };
}

export function applyIntentEvent(prev: StreamingState, event: IntentEvent): StreamingState {
  return { ...prev, intent: event };
}

export function applyRoutingEvent(prev: StreamingState, event: RoutingEvent): StreamingState {
  return { ...prev, routing: event };
}

export function applyAgencyStartEvent(prev: StreamingState, event: AgencyStartEvent): StreamingState {
  const statuses = { ...prev.agencyStatuses };
  statuses[event.agency_id] = {
    agencyId: event.agency_id,
    agencyName: event.agency_name,
    query: event.query,
    sectionLabel: event.section_label,
    status: 'running',
  };
  return { ...prev, agencyStatuses: statuses };
}

export function applyAgencyRespondedEvent(prev: StreamingState, event: AgencyRespondedEvent): StreamingState {
  const statuses = { ...prev.agencyStatuses };
  const existing = statuses[event.agency_id] ?? {
    agencyId: event.agency_id,
    agencyName: event.agency_name,
    query: '',
    sectionLabel: event.section_label,
    status: 'pending' as const,
  };
  statuses[event.agency_id] = {
    ...existing,
    status: event.status === 'ok' ? 'ok' : 'error',
    errorType: event.error_type,
  };
  return { ...prev, agencyStatuses: statuses };
}

export function applyAgencyVerifiedEvent(prev: StreamingState, event: AgencyVerifiedEvent): StreamingState {
  const statuses = { ...prev.agencyStatuses };
  const existing = statuses[event.agency_id];
  if (existing) {
    statuses[event.agency_id] = {
      ...existing,
      status: event.status,
      relevanceScore: event.relevance_score,
    };
  }
  return { ...prev, agencyStatuses: statuses };
}

export function applyAnswerEvent(prev: StreamingState, event: AnswerEvent): StreamingState {
  return {
    ...prev,
    answer: event.answer,
    sections: event.sections,
    errors: event.errors,
    summary: event.summary?.trim() ? event.summary : null,
    summaryReferences: event.references ?? [],
  };
}

export function applyDoneEvent(prev: StreamingState, event: DoneEvent): StreamingState {
  return {
    ...prev,
    sessionId: event.session_id,
    totalMs: event.total_ms,
    threadName: event.thread_name ?? prev.threadName,
    messageId: event.message_id ?? prev.messageId,
    done: true,
  };
}

export function applyErrorEvent(prev: StreamingState, event: ErrorEvent): StreamingState {
  return {
    ...prev,
    errors: [...prev.errors, { agency: '', name: '', errorType: 'SSE', message: event.message }],
    done: true,
  };
}
