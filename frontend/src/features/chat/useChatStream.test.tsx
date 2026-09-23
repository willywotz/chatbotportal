import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { useChatStream } from './useChatStream';

vi.mock('@/features/chat/chatApi', () => ({
  sendChatQuerySSE: vi.fn(),
}));

import { sendChatQuerySSE } from '@/features/chat/chatApi';

const mockSSE = sendChatQuerySSE as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useChatStream startStream', () => {
  it('streams over SSE and reports usedSSE: true', async () => {
    mockSSE.mockResolvedValue(true);
    const { result } = renderHook(() => useChatStream());

    let outcome: { usedSSE: boolean; aborted: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.startStream({ query: 'hi' });
    });

    expect(mockSSE).toHaveBeenCalled();
    expect(outcome).toEqual({ usedSSE: true, aborted: false });
  });

  it('reports no stream handled the request when SSE returns false', async () => {
    mockSSE.mockResolvedValue(false);
    const { result } = renderHook(() => useChatStream());

    let outcome: { usedSSE: boolean; aborted: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.startStream({ query: 'hi' });
    });

    expect(outcome).toEqual({ usedSSE: false, aborted: false });
  });
});
