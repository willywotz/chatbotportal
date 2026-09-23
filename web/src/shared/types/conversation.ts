import type { SummaryReference } from './chat';

export interface ConversationMessage {
  id: string;
  role: string;
  content: string;
  agent_steps: any;
  sources: any;
  summary?: string | null;
  summary_references?: SummaryReference[];
  rating: string | null;
  created_at: string;
}
