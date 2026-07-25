import { memo, useState } from "react";
import { ThumbsUp, ThumbsDown, Brain, ChevronDown, ChevronUp, Bot } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { cn, parseThinkContent } from "@/shared/lib/utils";
import type { ChatMessage } from "@/shared/types";
import { SummaryCard } from "@/shared/components/SummaryCard";
import { stripSummaryPrefix } from "@/shared/lib/summary";
import { FeedbackDialog } from "./FeedbackDialog";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const MessageBubble = memo(function MessageBubble({ message, onRate }: { message: ChatMessage; onRate?: (id: string, rating: 'up' | 'down', feedbackText?: string) => void }) {
  const [showFeedback, setShowFeedback] = useState(false);
  const [thinkOpen, setThinkOpen] = useState(false);
  const isUser = message.role === 'user';
  const { thinking, answer } = isUser ? { thinking: '', answer: message.content } : parseThinkContent(message.content);

  const handleThumbsDown = () => {
    setShowFeedback(true);
  };

  const handleFeedbackSubmit = (text: string) => {
    onRate?.(message.id, 'down', text || undefined);
  };

  return (
    <div className={cn("flex gap-3 mb-4", isUser && "flex-row-reverse")}>
      {/* {isUser
        ? <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-sm bg-primary text-primary-foreground">👤</div>
        : <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 bg-primary/10 text-primary"><Bot className="h-4 w-4" /></div>} */}
      <div className={cn("max-w-[80%] space-y-2", isUser && "text-right")}>
        <div className={cn(
          "rounded-2xl px-4 py-3 text-[1em] leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-tr-sm"
            : "bg-card border border-border rounded-tl-sm"
        )}>
          {!isUser && thinking && (
            <div className="mb-2 rounded-lg border border-border bg-muted/40 overflow-hidden">
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
          {isUser ? (
            <div className="whitespace-pre-wrap">{answer}</div>
          ) : (
            <>
              <SummaryCard summary={message.summary} references={message.summaryReferences} />
              <div className="prose prose-sm text-[0.875em] dark:prose-invert max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-table:my-2 prose-hr:my-3">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{stripSummaryPrefix(answer, message.summary)}</ReactMarkdown>
              </div>
            </>
          )}
        </div>
        {!isUser && message.sources && (
          <div className="flex flex-wrap gap-1.5">
            {message.sources.map((src, i) => (
              <a key={i} href={src.url} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[10px] bg-accent text-accent-foreground px-2 py-1 rounded-full hover:bg-accent/80 transition-colors">
                📎 {src.agency}: {src.title}
              </a>
            ))}
          </div>
        )}
        {!isUser && onRate && (
          <div className="flex items-center gap-1">
            {message.rating ? (
              <span className="text-xs text-muted-foreground">
                {message.rating === 'up' ? '👍 ขอบคุณสำหรับ feedback!' : '👎 ขอบคุณ จะปรับปรุงต่อไป'}
              </span>
            ) : (
              <>
                <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full" onClick={() => onRate(message.id, 'up')}>
                  <ThumbsUp className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="icon" className="h-7 w-7 rounded-full" onClick={handleThumbsDown}>
                  <ThumbsDown className="h-3.5 w-3.5" />
                </Button>
              </>
            )}
          </div>
        )}
        <p className="text-[10px] text-muted-foreground">{message.timestamp}</p>
      </div>

      <FeedbackDialog
        open={showFeedback}
        onClose={() => setShowFeedback(false)}
        onSubmit={handleFeedbackSubmit}
      />
    </div>
  );
});
