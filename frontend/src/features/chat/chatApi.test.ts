import { http, HttpResponse } from 'msw';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { server } from '@/mocks/server';
import { STREAM_IDLE_TIMEOUT_MS } from '@/shared/constants/query';

import { sendChatQuery, sendChatQuerySSE } from './chatApi';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sseChunk(event: string, data: unknown): Uint8Array {
  const text = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  return new TextEncoder().encode(text);
}

/**
 * Returns an MSW handler for POST /api/v1/chat that:
 * 1. Immediately enqueues `initialChunk` into the stream.
 * 2. Never closes the stream (simulating a hung server).
 */
function makeHangingSSEHandler(initialChunk: Uint8Array): ReturnType<typeof http.post> {
  return http.post('*/api/v1/chat', () => {
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(initialChunk);
        // Do NOT call c.close() — hang forever
      },
    });

    return new HttpResponse(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  });
}

/**
 * Returns an MSW handler for POST /api/v1/chat that emits one step
 * event and then immediately closes the stream (normal happy path).
 */
function makeCompletingSSEHandler(): ReturnType<typeof http.post> {
  return http.post('*/api/v1/chat', () => {
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(sseChunk('step', { step: 'thinking' }));
        c.enqueue(sseChunk('done', { sessionId: 'sess-1', answer: 'Hello!' }));
        c.close();
      },
    });

    return new HttpResponse(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  });
}

// ---------------------------------------------------------------------------
// SSE idle timeout (Task 4)
// ---------------------------------------------------------------------------

describe('sendChatQuerySSE — idle timeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('cancels the reader and does NOT call onError when stream hangs past STREAM_IDLE_TIMEOUT_MS', async () => {
    server.use(makeHangingSSEHandler(sseChunk('step', { step: 'thinking' })));

    // Spy on ReadableStreamDefaultReader.prototype.cancel to detect stream teardown
    const cancelSpy = vi.spyOn(ReadableStreamDefaultReader.prototype, 'cancel');

    const onError = vi.fn();
    const onStep = vi.fn();

    const promise = sendChatQuerySSE(
      { query: 'test' },
      { onStep, onError },
    );

    // Let the first step event arrive (flush microtasks/promises)
    await vi.advanceTimersByTimeAsync(0);

    // Advance past the idle timeout
    await vi.advanceTimersByTimeAsync(STREAM_IDLE_TIMEOUT_MS + 1);

    await promise;

    // The step event was received before the hang
    expect(onStep).toHaveBeenCalledTimes(1);
    // Idle timeout does NOT call onError — routes to connection-lost via !state.done
    expect(onError).not.toHaveBeenCalled();
    // The reader must have been cancelled to tear down the underlying stream/connection
    expect(cancelSpy).toHaveBeenCalledTimes(1);

    cancelSpy.mockRestore();
  }, 15_000);

  it('does NOT fire onError when stream completes normally within the timeout', async () => {
    server.use(makeCompletingSSEHandler());

    const onError = vi.fn();
    const onStep = vi.fn();
    const onDone = vi.fn();

    const promise = sendChatQuerySSE(
      { query: 'test' },
      { onStep, onError, onDone },
    );

    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(STREAM_IDLE_TIMEOUT_MS - 1000);

    await promise;

    expect(onStep).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it('posts to /api/v1/chat with stream: true in the request body', async () => {
    let capturedBody: unknown;
    server.use(
      http.post('*/api/v1/chat', async ({ request }) => {
        capturedBody = await request.json();
        const stream = new ReadableStream<Uint8Array>({
          start(c) {
            c.enqueue(sseChunk('done', { sessionId: 'sess-1' }));
            c.close();
          },
        });
        return new HttpResponse(stream, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        });
      }),
    );

    await sendChatQuerySSE({ query: 'test' }, {});

    expect(capturedBody).toEqual({ query: 'test', stream: true });
  });

  it('sends credentials: include and no Authorization header', async () => {
    server.use(makeCompletingSSEHandler());
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    await sendChatQuerySSE({ query: 'test' }, {});

    const [, options] = fetchSpy.mock.calls[0];
    expect(options?.credentials).toBe('include');
    expect((options?.headers as Record<string, string> | undefined)?.Authorization).toBeUndefined();

    fetchSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// sendChatQuery — unified envelope
// ---------------------------------------------------------------------------

describe('sendChatQuery', () => {
  it('posts to /api/v1/chat with no stream flag and parses the unified envelope', async () => {
    let capturedBody: unknown;
    server.use(
      http.post('*/api/v1/chat', async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          success: true,
          data: {
            message_id: 'msg-1',
            cached: false,
            agentSteps: [{ name: 'discover', status: 'done' }],
            answer: 'Hello!',
          },
          conversation_id: 'conv-1',
          responseTime: 42,
        });
      }),
    );

    const result = await sendChatQuery({ query: 'test' });

    expect(capturedBody).toEqual({ query: 'test' });
    expect(result.data.answer).toBe('Hello!');
    expect(result.data.agentSteps).toEqual([{ name: 'discover', status: 'done' }]);
    expect(result.data.message_id).toBe('msg-1');
  });
});
