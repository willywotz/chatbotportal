import { Send, Search, ArrowRight, ArrowLeft } from 'lucide-react';
import { Button } from '@/shared/components/ui/button';
import { SidebarProvider, SidebarTrigger } from '@/shared/components/ui/sidebar';
import { ChatConversation } from '@/features/chat/ChatConversation';
import { ChatInput } from '@/features/chat/ChatInput';
import { LandingHero } from '@/features/public/LandingHero';
import { PublicSidebar } from '@/features/public/PublicSidebar';
import { SuggestedQuestions } from '@/features/public/SuggestedQuestions';
import { AgencyCards } from '@/features/public/AgencyCards';
import { InfoLinks } from '@/features/public/InfoLinks';
import { TextScaleControl } from '@/shared/components/TextScaleControl';
import { useChat } from '@/features/chat/useChat';
import { usePublicPopularQuestions } from '@/features/popular-questions/popularQuestionsApi';
import { usePublicAgencies } from '@/features/public/publicAgenciesApi';
import { useState } from 'react';
import { Link } from 'react-router-dom';

export default function PublicPortal() {
  const {
    messages, input, setInput, isTyping, activeStepCount, currentSteps,
    streamingState, scrollRef, handleSend, handleRate, reset, cancelStream, hasMessages,
  } = useChat();
  const { data: popularQuestions } = usePublicPopularQuestions();
  const { data: publicAgencies } = usePublicAgencies();
  const [chatMode, setChatMode] = useState(false);

  const isStreaming = isTyping && streamingState.pipelineSteps.length > 0 && !streamingState.done;

  const onSend = (text?: string) => {
    if (!chatMode) setChatMode(true);
    handleSend(text);
  };

  const handleBack = () => {
    setChatMode(false);
    reset();
  };

  const loginButton = (
    <Button asChild variant="outline" size="sm" className="rounded-full bg-white">
      <Link to="/login">
        เข้าสู่ระบบ <ArrowRight className="w-3 h-3" />
      </Link>
    </Button>
  );

  if (chatMode) {
    return (
      <SidebarProvider>
        <PublicSidebar agencies={publicAgencies ?? []} onNewChat={reset} />
        <div className="flex-1 flex flex-col min-w-0 min-h-svh bg-background">
          {/* Header */}
          <header className="px-6 py-3 flex items-center justify-between sticky top-0 z-10">
            <div className="flex items-center gap-2.5">
              <SidebarTrigger />
              <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={handleBack}>
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <TextScaleControl />
              {loginButton}
            </div>
          </header>

          <ChatConversation
            messages={messages} isTyping={isTyping} isStreaming={isStreaming}
            activeStepCount={activeStepCount} currentSteps={currentSteps}
            streamingState={streamingState} scrollRef={scrollRef} onRate={handleRate} />
          <ChatInput
            input={input} setInput={setInput} isTyping={isTyping}
            onSend={() => onSend()} onCancel={cancelStream} />
        </div>
      </SidebarProvider>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="px-6 py-3 flex items-center justify-end gap-2 sticky top-0 z-10">
        {loginButton}
      </header>

      <>
          <main className="flex-1 flex flex-col items-center justify-center px-4 py-16">
            <LandingHero />

            {/* Search */}
            <div className="w-full max-w-xl mb-12">
              <p className="text-xs text-muted-foreground mb-2 ml-1">ถามคำถามเกี่ยวกับบริการภาครัฐ</p>
              <div className="relative flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input value={input} onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && onSend()}
                    placeholder="พิมพ์คำถามของคุณ เช่น ขั้นตอนทำบัตรประชาชนใหม่..."
                    className="w-full bg-card border border-input rounded-2xl pl-11 pr-4 py-4 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary shadow-sm transition-shadow focus:shadow-md" />
                </div>
                <Button onClick={() => onSend()} size="icon" className="rounded-2xl h-[52px] w-[52px] shrink-0 shadow-sm" disabled={!input.trim()}>
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {popularQuestions && popularQuestions.length > 0 && (
              <SuggestedQuestions questions={popularQuestions} onSelect={onSend} />
            )}

            {publicAgencies && publicAgencies.length > 0 && (
              <section className="w-full max-w-4xl mt-12">
                <h2 className="text-sm font-semibold text-foreground text-center mb-5">หน่วยงานที่เชื่อมต่อ</h2>
                <AgencyCards agencies={publicAgencies} />
              </section>
            )}
          </main>

          <footer className="border-t border-border py-6 px-6">
            <div className="max-w-xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">© 2568 Agentic AI Chatbot</span>
              </div>
              <InfoLinks />
            </div>
          </footer>
        </>
    </div>
  );
}
