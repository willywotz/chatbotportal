import type { RefObject } from 'react';
import type { AgentStep, ChatMessage } from '@/shared/types';
import type { StreamingState } from '@/shared/types/chat';
import { ScrollArea } from '@/shared/components/ui/scroll-area';
import { AgentStepsCard } from '@/shared/components/AgentStepsCard';
import { ASSISTANT_BUBBLE_CLASS } from '@/shared/components/AssistantMessageContent';
import { cn } from '@/shared/lib/utils';
import { buildAgentStepsSnapshot } from '@/features/chat/chatHelpers';
import { MessageBubble } from '@/features/chat/MessageBubble';
import { useTextScale } from '@/shared/hooks/useTextScale';

interface ChatConversationProps {
  messages: ChatMessage[];
  isTyping: boolean;
  isStreaming: boolean;
  activeStepCount: number;
  currentSteps: AgentStep[];
  streamingState: StreamingState;
  scrollRef: RefObject<HTMLDivElement>;
  onRate: (id: string, rating: 'up' | 'down', feedbackText?: string) => void;
}

export function ChatConversation({
  messages, isTyping, streamingState, scrollRef, onRate,
}: ChatConversationProps) {
  const { factor } = useTextScale();
  const liveSteps = buildAgentStepsSnapshot(streamingState);
  return (
    <ScrollArea className="flex-1 p-4">
      <div className="max-w-3xl mx-auto" style={{ fontSize: `${factor}em` }}>
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onRate={onRate} />
        ))}
        {isTyping && (
          liveSteps ? (
            <div className="mb-4 max-w-[80%]">
              <AgentStepsCard steps={liveSteps} defaultOpen />
            </div>
          ) : (
            <div className="flex items-start gap-3 mb-4">
              <div className={cn(ASSISTANT_BUBBLE_CLASS, "max-w-[75%]")}>
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )
        )}
        <div ref={scrollRef} />
      </div>
    </ScrollArea>
  );
}
