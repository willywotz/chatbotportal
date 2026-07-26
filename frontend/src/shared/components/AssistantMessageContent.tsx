import { useState } from "react";
import { Brain, ChevronDown, ChevronUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AgentStepsCard } from "@/shared/components/AgentStepsCard";
import { SummaryCard } from "@/shared/components/SummaryCard";
import { stripSummaryPrefix } from "@/shared/lib/summary";
import { parseThinkContent } from "@/shared/lib/utils";
import type { AgentStepsSnapshot, SummaryReference } from "@/shared/types/chat";

/** Card-bubble styling for an assistant answer, shared with the typing placeholder. */
export const ASSISTANT_BUBBLE_CLASS =
  "rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3 text-[1em] leading-relaxed";

/**
 * Shared presentation for an assistant reply: a collapsible thinking panel, the
 * markdown answer, and the executive summary card. Used by both live chat
 * (MessageBubble) and history (MessageItem) so the two never drift.
 */
export function AssistantMessageContent({
  content,
  summary,
  references,
  steps,
}: {
  content: string;
  summary?: string | null;
  references?: SummaryReference[];
  steps?: AgentStepsSnapshot | null;
}) {
  const [thinkOpen, setThinkOpen] = useState(true);
  const { thinking, answer } = parseThinkContent(content);

  return (
    <>
      {thinking && (
        <div className="rounded-lg border border-border bg-muted/40 overflow-hidden">
          <button
            onClick={() => setThinkOpen((o) => !o)}
            className="flex w-full items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <Brain className="h-3.5 w-3.5 shrink-0" />
            <span className="font-medium">Thinking</span>
            {thinkOpen ? <ChevronUp className="ml-auto h-3.5 w-3.5" /> : <ChevronDown className="ml-auto h-3.5 w-3.5" />}
          </button>
          {thinkOpen && (
            <div className="px-3 pb-3 text-xs text-muted-foreground whitespace-pre-wrap border-t border-border pt-2">
              {thinking}
            </div>
          )}
        </div>
      )}
      <AgentStepsCard steps={steps ?? null} />
      <div className={ASSISTANT_BUBBLE_CLASS}>
        <div className="prose prose-sm text-[0.875em] dark:prose-invert max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-table:my-2 prose-hr:my-3">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{stripSummaryPrefix(answer, summary)}</ReactMarkdown>
        </div>
      </div>
      <SummaryCard summary={summary} references={references} />
    </>
  );
}
