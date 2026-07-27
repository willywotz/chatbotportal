# Cross-service trace verification

## Purpose
Confirm trace propagation across Portal backend and agent-proxy, and determine
empirically whether OneChat forwards the W3C `traceparent` header.

## Steps
1. Bring up the stack: `rtk docker compose up -d` (includes Jaeger).
2. Send a chat request with a known trace id:
   ```bash
   curl -N http://localhost/api/v1/chat/stream \
     -H 'Content-Type: application/json' \
     -H 'traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01' \
     -d '{"query":"hello"}'
   ```
3. Open the Jaeger UI (http://localhost:16686). Search by trace id
   `0af7651916cd43dd8448eb211c80319c`.

## Interpreting results
- **Single trace, all services present** (backend `chat_stream`, `onechat_call`,
  MCP span, `agent-proxy`): OneChat forwards `traceparent`. Goal fully met.
- **Multiple traces**: OneChat drops the header on its outbound calls. Fall back to
  correlation: in Jaeger, search by tag `conversation_id=<id from the done event>`
  to list every fragment across services.

## What each change guarantees
- Backend outbound always injects `traceparent` (backend `HTTPXClientInstrumentor`).
- `/mcp` and agent-proxy always continue an inbound `traceparent` when present
  (ASGI middleware on the mount; Go propagator + extract).
- Every service stamps `conversation_id`, so fragments are always joinable by tag
  regardless of OneChat's behavior.
