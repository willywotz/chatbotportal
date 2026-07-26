import { memo, useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import type { ChatMessage } from "@/shared/types";
import { AssistantMessageContent } from "@/shared/components/AssistantMessageContent";
import { FeedbackDialog } from "./FeedbackDialog";

export const MessageBubble = memo(function MessageBubble({ message, onRate }: { message: ChatMessage; onRate?: (id: string, rating: 'up' | 'down', feedbackText?: string) => void }) {
  const [showFeedback, setShowFeedback] = useState(false);
  const isUser = message.role === 'user';

  const handleThumbsDown = () => {
    setShowFeedback(true);
  };

  const handleFeedbackSubmit = (text: string) => {
    onRate?.(message.id, 'down', text || undefined);
  };

  return (
    <div className={cn("flex gap-3 mb-4", isUser && "flex-row-reverse")}>
      <div className={cn("max-w-[80%] space-y-2", isUser && "text-right")}>
        {isUser ? (
          <div className="rounded-2xl rounded-tr-sm bg-primary px-4 py-3 text-[1em] leading-relaxed text-primary-foreground">
            <div className="whitespace-pre-wrap">{message.content}</div>
          </div>
        ) : (
          <AssistantMessageContent
            content={message.content}
            summary={message.summary}
            references={message.summaryReferences}
            steps={message.pipeline}
          />
        )}
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
