import type { AgentStep } from './agency';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  agentSteps?: AgentStep[];
  sources?: { agency: string; url: string; title: string }[];
  rating?: 'up' | 'down' | null;
  summary?: string | null;
  summaryReferences?: SummaryReference[];
  pipeline?: AgentStepsSnapshot | null;
}

export interface ConversationHistory {
  id: string;
  title: string;
  preview: string;
  date: string;
  agencies: string[];
  status: 'success' | 'failed';
  messages: ChatMessage[];
}

// --- v4 SSE Streaming Types ---

export type PipelineStepName = 'discover' | 'classify' | 'invoke' | 'verify' | 'summarize' | 'synthesize';

export interface SummaryReference {
  number: number;
  agency_id: string;
  agency_name: string;
  url: string | null;
}

export interface AgentStepsSnapshot {
  steps: { name: string; ms: number | null }[];
  agencies: {
    id: string;
    name: string | null;
    status: AgencyStatus;
    errorType?: string | null;
    relevanceScore?: number | null;
    sectionLabel?: string | null;
  }[];
  errors: { agency: string; name: string; errorType: string; message: string }[];
}

export interface StepEvent {
  name: PipelineStepName;
  status: 'running' | 'done';
  ms: number | null;
}

export interface AgenciesEvent {
  agencies: {
    id: string;
    name: string;
    description: string | null;
    data_scope: string[];
  }[];
  count: number;
}

export interface IntentEvent {
  intent: 'search' | 'chitchat' | 'capability';
  normalized_query: string | null;
  reasoning: string | null;
}

export interface RoutingSubQuestion {
  section_label: string;
  broadcast: boolean;
  agencies: { id: string; name: string; query: string }[];
}

export interface RoutingEvent {
  sub_questions: RoutingSubQuestion[];
}

export type AgencyStatus = 'pending' | 'running' | 'ok' | 'error' | 'passed' | 'rejected';

export interface AgencyStartEvent {
  agency_id: string;
  agency_name: string | null;
  query: string;
  section_label: string | null;
}

export interface AgencyRespondedEvent {
  agency_id: string;
  agency_name: string | null;
  status: 'ok' | 'error';
  section_label: string | null;
  error_type: string | null;
}

export interface AgencyVerifiedEvent {
  agency_id: string;
  agency_name: string | null;
  status: 'passed' | 'rejected';
  relevance_score: number | null;
  section_label: string | null;
}

export interface AnswerSection {
  title: string;
  agencies: { id: string; name: string; query: string; content: string }[];
}

export interface AnswerEvent {
  answer: string;
  summary?: string;
  references?: SummaryReference[];
  sections: AnswerSection[];
  errors: { agency: string; name: string; errorType: string; message: string }[];
  debug: Record<string, unknown> | null;
}

export interface DoneEvent {
  session_id: string;
  total_ms: number;
  message_id?: string;
  thread_name?: string | null;
}

export interface ErrorEvent {
  message: string;
  code: number;
}

// Streaming state for UI rendering
export interface PipelineStepState {
  name: PipelineStepName;
  status: 'running' | 'done';
  ms: number | null;
}

export interface AgencyState {
  agencyId: string;
  agencyName: string | null;
  query: string;
  sectionLabel: string | null;
  status: AgencyStatus;
  errorType?: string | null;
  relevanceScore?: number | null;
}

export interface StreamingState {
  pipelineSteps: PipelineStepState[];
  currentStep: PipelineStepName | null;
  agencies: AgenciesEvent['agencies'];
  intent: IntentEvent | null;
  routing: RoutingEvent | null;
  agencyStatuses: Record<string, AgencyState>;
  answer: string | null;
  sections: AnswerSection[];
  errors: AnswerEvent['errors'];
  summary: string | null;
  summaryReferences: SummaryReference[];
  threadName: string | null;
  sessionId: string | null;
  messageId: string | null;
  totalMs: number | null;
  done: boolean;
}