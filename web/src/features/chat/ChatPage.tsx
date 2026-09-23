import { useEffect } from 'react';
import { ScrollArea } from '@/shared/components/ui/scroll-area';
import { useSearchParams } from 'react-router-dom';
import { ChatConversation } from '@/features/chat/ChatConversation';
import { ChatInput } from '@/features/chat/ChatInput';
import { useChat } from '@/features/chat/useChat';
import { usePublicPopularQuestions } from '@/features/popular-questions/popularQuestionsApi';
import { SuggestedQuestions } from '@/features/public/SuggestedQuestions';

export default function ChatPage() {
  const {
    messages, input, setInput, isTyping, activeStepCount, currentSteps,
    streamingState, scrollRef, handleSend, handleRate, reset, cancelStream, hasMessages,
  } = useChat();
  const { data: popularQuestions } = usePublicPopularQuestions();
  const [searchParams, setSearchParams] = useSearchParams();

  const isStreaming = isTyping && streamingState.pipelineSteps.length > 0 && !streamingState.done;

  useEffect(() => {
    const q = searchParams.get('q');
    if (q) {
      setSearchParams({});
      handleSend(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Start a fresh conversation when แชทใหม่ is clicked while already on /chat.
  useEffect(() => {
    if (searchParams.get('new')) {
      reset();
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, reset, setSearchParams]);

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {!hasMessages && !isTyping ? (
        <ScrollArea className="flex-1 p-4">
          <div className="flex flex-col items-center justify-center h-full min-h-[60vh] text-center px-4">
            <h1 className="text-3xl md:text-4xl !leading-normal font-bold text-center mb-3 portal-gradient-text">
              Agentic AI Chatbot
            </h1>
            <p className="text-sm md:text-base text-muted-foreground text-center max-w-lg mb-10 leading-relaxed">
              สอบถามข้อมูลจากหน่วยงานภาครัฐได้ครบในที่เดียวสำหรับประชาชน
            </p>
            {popularQuestions && popularQuestions.length > 0 && (
              <SuggestedQuestions questions={popularQuestions} onSelect={handleSend} />
            )}
          </div>
        </ScrollArea>
      ) : (
        <ChatConversation
          messages={messages} isTyping={isTyping} isStreaming={isStreaming}
          activeStepCount={activeStepCount} currentSteps={currentSteps}
          streamingState={streamingState} scrollRef={scrollRef} onRate={handleRate} />
      )}

      <ChatInput
        input={input} setInput={setInput} isTyping={isTyping}
        onSend={() => handleSend()} onCancel={cancelStream} />
    </div>
  );
}
