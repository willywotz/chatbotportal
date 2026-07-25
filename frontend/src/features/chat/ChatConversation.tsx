import type { RefObject } from 'react';
import type { AgentStep, ChatMessage } from '@/shared/types';
import type { StreamingState } from '@/shared/types/chat';
import { ScrollArea } from '@/shared/components/ui/scroll-area';
import { MessageBubble } from '@/features/chat/MessageBubble';
import { AgentStepDisplay, StreamingProgress } from '@/features/chat/AgentStepDisplay';
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
  messages, isTyping, isStreaming, activeStepCount, currentSteps,
  streamingState, scrollRef, onRate,
}: ChatConversationProps) {
  const { factor } = useTextScale();
  return (
    <ScrollArea className="flex-1 p-4">
      <div className="max-w-3xl mx-auto" style={{ zoom: factor }}>
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onRate={onRate} />
        ))}
        {isTyping && (
          <div className="flex items-start gap-3 mb-4">
            <div className="bg-card border border-border rounded-2xl rounded-tl-sm px-4 py-3 max-w-[75%]">
              {isStreaming ? (
                <StreamingProgress state={streamingState} />
              ) : activeStepCount > 0 ? (
                <AgentStepDisplay steps={currentSteps} visibleCount={activeStepCount} />
              ) : (
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              )}
            </div>
          </div>
        )}
        <div ref={scrollRef} />
      </div>
    </ScrollArea>
  );
}
