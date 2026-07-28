import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { useChatStream } from './useChatStream';

vi.mock('@/features/chat/chatApi', () => ({
  sendChatQueryWS: vi.fn(),
  sendChatQuerySSE: vi.fn(),
}));

import { sendChatQueryWS, sendChatQuerySSE } from '@/features/chat/chatApi';

const mockWS = sendChatQueryWS as ReturnType<typeof vi.fn>;
const mockSSE = sendChatQuerySSE as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useChatStream startStream', () => {
  it('tries WS first and skips SSE when WS returns true', async () => {
    mockWS.mockResolvedValue(true);
    const { result } = renderHook(() => useChatStream());

    let outcome: { usedSSE: boolean; aborted: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.startStream({ query: 'hi' });
    });

    expect(mockWS).toHaveBeenCalled();
    expect(mockSSE).not.toHaveBeenCalled();
    expect(outcome).toEqual({ usedSSE: true, aborted: false });
  });

  it('falls back to SSE only when WS returns false', async () => {
    mockWS.mockResolvedValue(false);
    mockSSE.mockResolvedValue(true);
    const { result } = renderHook(() => useChatStream());

    let outcome: { usedSSE: boolean; aborted: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.startStream({ query: 'hi' });
    });

    expect(mockWS).toHaveBeenCalled();
    expect(mockSSE).toHaveBeenCalled();
    expect(outcome).toEqual({ usedSSE: true, aborted: false });
  });

  it('reports no stream handled the request when both WS and SSE return false', async () => {
    mockWS.mockResolvedValue(false);
    mockSSE.mockResolvedValue(false);
    const { result } = renderHook(() => useChatStream());

    let outcome: { usedSSE: boolean; aborted: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.startStream({ query: 'hi' });
    });

    expect(outcome).toEqual({ usedSSE: false, aborted: false });
  });
});
