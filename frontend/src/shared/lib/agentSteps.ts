import type { AgentStepsSnapshot } from '@/shared/types/chat';

interface RawStep {
  name: string;
  ms: number | null;
}

interface RawAgency {
  id: string;
  name: string | null;
  status: AgentStepsSnapshot['agencies'][number]['status'];
  error_type?: string | null;
  relevance_score?: number | null;
  section_label?: string | null;
}

interface RawError {
  agency: string;
  name: string;
  error_type: string;
  message: string;
}

interface RawSnapshot {
  steps?: RawStep[];
  agencies?: RawAgency[];
  errors?: RawError[];
}

/**
 * Normalize a persisted `agent_steps` value (snake_case object, or the legacy
 * `[]` default) into an AgentStepsSnapshot. Returns null when there is nothing
 * worth showing, so callers can conditionally render the card.
 */
export function toAgentStepsSnapshot(raw: unknown): AgentStepsSnapshot | null {
  if (!raw || Array.isArray(raw) || typeof raw !== 'object') return null;
  const { steps = [], agencies = [], errors = [] } = raw as RawSnapshot;

  const mappedSteps = steps.map((s) => ({ name: s.name, ms: s.ms ?? null }));
  const mappedAgencies = agencies.map((a) => ({
    id: a.id,
    name: a.name ?? null,
    status: a.status,
    errorType: a.error_type ?? null,
    relevanceScore: a.relevance_score ?? null,
    sectionLabel: a.section_label ?? null,
  }));
  const mappedErrors = errors.map((e) => ({
    agency: e.agency,
    name: e.name,
    errorType: e.error_type,
    message: e.message,
  }));

  if (!mappedSteps.length && !mappedAgencies.length && !mappedErrors.length) return null;
  return { steps: mappedSteps, agencies: mappedAgencies, errors: mappedErrors };
}
