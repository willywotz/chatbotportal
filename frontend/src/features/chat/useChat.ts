import { useState, useRef, useEffect, useCallback } from 'react';
import type { ChatMessage, AgentStep } from '@/shared/types';
import { useAuth } from '@/features/auth/useAuth';
import { sendChatQuery } from '@/features/chat/chatApi';
import { updateMessageRating } from '@/features/chat/feedbackApi';
import { mockAgentSteps } from '@/shared/data/mockData';
import { generateUniqueId } from '@/shared/lib/utils';
import {
  buildAiMessageFromState,
  buildConnectionLostMessage,
  buildGenericErrorMessage,
  formatTimestamp,
} from './chatHelpers';
import { useChatStream } from './useChatStream';

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [activeStepCount, setActiveStepCount] = useState(0);
  const [currentSteps, setCurrentSteps] = useState<AgentStep[]>(mockAgentSteps);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { ensureSession } = useAuth();
  const { streamingState, streamingRef, abortRef, startStream, cancelStream: streamCancel, resetStream } = useChatStream();

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activeStepCount, streamingState.currentStep]);

  // B6: optimistic update with rollback on API failure
  const handleRate = useCallback(async (id: string, rating: 'up' | 'down', feedbackText?: string) => {
    let previousRating: 'up' | 'down' | null | undefined;
    setMessages((prev) => {
      const msg = prev.find((m) => m.id === id);
      previousRating = msg?.rating;
      return prev.map((m) => (m.id === id ? { ...m, rating } : m));
    });
    const ok = await updateMessageRating(id, rating, feedbackText);
    if (!ok) {
      // Roll back to previous rating
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, rating: previousRating ?? null } : m))
      );
    }
  }, []);

  const cancelStream = useCallback(() => {
    streamCancel();
    setIsTyping(false);
    setActiveStepCount(0);
  }, [streamCancel]);

  const finalizeStreaming = useCallback(() => {
    // Read from streamingRef.current (always synchronous / latest) — same as original.
    const state = streamingRef.current;
    state.sessionId && setConversationId(state.sessionId);
    const aiMsg = buildAiMessageFromState(state);
    if (aiMsg) {
      setMessages((prev) => [...prev, aiMsg]);
    } else if (state.done && state.errors.length > 0) {
      // B8/S1: SSE error event set done=true with no answer — surface an error bubble
      setMessages((prev) => [...prev, buildGenericErrorMessage()]);
    } else if (!state.done) {
      // Stream ended without answer or done — connection lost
      setMessages((prev) => [...prev, buildConnectionLostMessage()]);
    }
    setIsTyping(false);
    setActiveStepCount(0);
  }, [streamingRef]);

  const handleSend = useCallback(async (text?: string) => {
    const question = text || input.trim();
    if (!question || isTyping) return;

    const userMsg: ChatMessage = {
      id: generateUniqueId(),
      role: 'user',
      content: question,
      timestamp: formatTimestamp(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);
    setActiveStepCount(0);

    try {
      await ensureSession();
      const { usedSSE, aborted } = await startStream({
        query: question,
        conversation_id: conversationId || undefined,
      });

      if (aborted) return;

      if (usedSSE) {
        finalizeStreaming();
        return;
      }

      const response = await sendChatQuery({ query: question, conversation_id: conversationId || undefined });

      if (response.success) {
        setConversationId(response.conversation_id);
        setCurrentSteps(response.data.agentSteps as AgentStep[]);
        setActiveStepCount(response.data.agentSteps.length);

        const aiMsgId = response.data.message_id || generateUniqueId();
        const aiMsg: ChatMessage = {
          id: aiMsgId,
          role: 'assistant',
          content: response.data.answer ?? response.data.summary ?? '',
          timestamp: formatTimestamp(),
          agentSteps: response.data.agentSteps as AgentStep[],
          sources: (response.data.references ?? []).map((ref) => ({
            agency: ref.agency ?? ref.agency_name ?? '',
            url: ref.url ?? '',
            title: ref.title ?? ref.agency_name ?? '',
          })),
          rating: null,
        };
        setMessages((prev) => [...prev, aiMsg]);
        setIsTyping(false);
        setActiveStepCount(0);
        return;
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;

      setCurrentSteps([]);
      setActiveStepCount(0);
      setIsTyping(false);
      // B8: reset stale streaming state so pipeline steps don't leak into the next send
      resetStream();
      setMessages((prev) => [...prev, buildGenericErrorMessage()]);
    }
  }, [input, isTyping, finalizeStreaming, startStream, conversationId, resetStream, ensureSession]);

  const reset = useCallback(() => {
    setMessages([]);
    setIsTyping(false);
    setActiveStepCount(0);
    setInput('');
    setCurrentSteps(mockAgentSteps);
    setConversationId(null);
    resetStream();
  }, [resetStream]);

  return {
    messages,
    input,
    setInput,
    isTyping,
    activeStepCount,
    currentSteps,
    streamingState,
    scrollRef,
    handleSend,
    handleRate,
    reset,
    cancelStream,
    hasMessages: messages.length > 0,
  };
}
