import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { sendChatQueryWS } from './chatApi';
import type { DoneEvent, StepEvent } from '@/shared/types/chat';

/** A minimal fake WebSocket the test drives manually via onopen/onmessage/onclose/onerror. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    // no-op — tests drive onclose explicitly
  }
}

describe('sendChatQueryWS', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the request JSON on open', async () => {
    const promise = sendChatQueryWS({ query: 'hi' }, {});
    const ws = FakeWebSocket.instances[0];
    ws.onopen?.();
    expect(ws.sent).toEqual([JSON.stringify({ query: 'hi' })]);
    ws.onmessage?.({ data: JSON.stringify({ event: 'done', data: { session_id: 's1', total_ms: 1 } }) });
    await promise;
  });

  it('dispatches each frame to the matching callback and resolves true on done', async () => {
    const onStep = vi.fn();
    const onDone = vi.fn();
    const promise = sendChatQueryWS({ query: 'hi' }, { onStep, onDone });
    const ws = FakeWebSocket.instances[0];
    ws.onopen?.();

    const step: StepEvent = { name: 'discover', status: 'running', ms: null };
    ws.onmessage?.({ data: JSON.stringify({ event: 'step', data: step }) });
    expect(onStep).toHaveBeenCalledWith(step);

    const done: DoneEvent = { session_id: 's1', total_ms: 5 };
    ws.onmessage?.({ data: JSON.stringify({ event: 'done', data: done }) });
    expect(onDone).toHaveBeenCalledWith(done);

    await expect(promise).resolves.toBe(true);
  });

  it('resolves false when the socket closes before any frame arrives', async () => {
    const promise = sendChatQueryWS({ query: 'hi' }, {});
    const ws = FakeWebSocket.instances[0];
    ws.onopen?.();
    ws.onclose?.();
    await expect(promise).resolves.toBe(false);
  });

  it('resolves true (no fallback) and calls onError when the socket closes after frames but before done', async () => {
    const onError = vi.fn();
    const onStep = vi.fn();
    const promise = sendChatQueryWS({ query: 'hi' }, { onStep, onError });
    const ws = FakeWebSocket.instances[0];
    ws.onopen?.();

    ws.onmessage?.({ data: JSON.stringify({ event: 'step', data: { name: 'discover', status: 'running', ms: null } }) });
    ws.onclose?.();

    await expect(promise).resolves.toBe(true);
    expect(onError).not.toHaveBeenCalled();
  });
});
