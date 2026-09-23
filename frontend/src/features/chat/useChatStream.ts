import { useState, useRef, useEffect, useCallback } from 'react';
import type { StreamingState } from '@/shared/types';
import { sendChatQuerySSE } from '@/features/chat/chatApi';
import type { ChatApiRequest } from '@/features/chat/chatApi';
import {
  INITIAL_STREAMING_STATE,
  applyStepEvent,
  applyAgenciesEvent,
  applyIntentEvent,
  applyRoutingEvent,
  applyAgencyStartEvent,
  applyAgencyRespondedEvent,
  applyAgencyVerifiedEvent,
  applyAnswerEvent,
  applyDoneEvent,
  applyErrorEvent,
} from './chatHelpers';

export interface UseChatStreamResult {
  streamingState: StreamingState;
  streamingRef: React.MutableRefObject<StreamingState>;
  abortRef: React.MutableRefObject<AbortController | null>;
  startStream: (request: ChatApiRequest) => Promise<{ usedSSE: boolean; aborted: boolean }>;
  cancelStream: () => void;
  resetStream: () => void;
}

export function useChatStream(): UseChatStreamResult {
  const [streamingState, setStreamingState] = useState<StreamingState>(INITIAL_STREAMING_STATE);
  const streamingRef = useRef<StreamingState>(INITIAL_STREAMING_STATE);
  const abortRef = useRef<AbortController | null>(null);

  // B7: abort in-flight SSE on unmount to prevent state updates after unmount
  useEffect(() => () => abortRef.current?.abort(), []);

  const cancelStream = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreamingState(INITIAL_STREAMING_STATE);
    streamingRef.current = INITIAL_STREAMING_STATE;
  }, []);

  const resetStream = useCallback(() => {
    setStreamingState(INITIAL_STREAMING_STATE);
    streamingRef.current = INITIAL_STREAMING_STATE;
    abortRef.current?.abort();
  }, []);

  const startStream = useCallback(async (request: ChatApiRequest): Promise<{ usedSSE: boolean; aborted: boolean }> => {
    const freshState = { ...INITIAL_STREAMING_STATE };
    setStreamingState(freshState);
    streamingRef.current = freshState;

    const abortController = new AbortController();
    abortRef.current = abortController;

    const applyAndSet = <E>(applyFn: (prev: StreamingState, event: E) => StreamingState) =>
      (event: E) => {
        const next = applyFn(streamingRef.current, event);
        streamingRef.current = next;
        setStreamingState(next);
      };

    const callbacks = {
      onStep: applyAndSet(applyStepEvent),
      onAgencies: applyAndSet(applyAgenciesEvent),
      onIntent: applyAndSet(applyIntentEvent),
      onRouting: applyAndSet(applyRoutingEvent),
      onAgencyStart: applyAndSet(applyAgencyStartEvent),
      onAgencyResponded: applyAndSet(applyAgencyRespondedEvent),
      onAgencyVerified: applyAndSet(applyAgencyVerifiedEvent),
      onAnswer: applyAndSet(applyAnswerEvent),
      onDone: applyAndSet(applyDoneEvent),
      onError: applyAndSet(applyErrorEvent),
    };

    const usedSSE = await sendChatQuerySSE(request, callbacks, abortController.signal);

    if (abortController.signal.aborted) {
      return { usedSSE, aborted: true };
    }

    return { usedSSE, aborted: false };
  }, []);

  return { streamingState, streamingRef, abortRef, startStream, cancelStream, resetStream };
}
