# Cross-service trace verification

## Purpose
Confirm that a chat round-trip shares **one** OpenTelemetry trace id across
`backend` and `agent-proxy`, even though OneChat sits between them and does not
forward the `traceparent` header.

## How unification works
OneChat drops the `traceparent` **header** between hops but **preserves URL query
strings** (verified empirically). So the W3C context is smuggled through the URLs
we hand OneChat:
- `stream.py` appends `?traceparent=<ctx>` to the `mcp_endpoint_url` sent to OneChat.
- `_agent_proxy_endpoint` appends it to the `/agent-proxy/{id}` callback URL.
- `QueryTraceparentASGI` (on the `/mcp` mount) promotes the query param back to a
  header before OTel extracts; agent-proxy extracts it from the query directly.
- A real `traceparent` header always takes precedence when present.

## Verify (live)
Requires the stack up with `ONECHAT_BASE_URL` set and nginx + the cloudflared
tunnel reachable (OneChat calls back through the tunnel → nginx).

1. Fire one chat with a known trace id (run from a container on the network, e.g.
   `docker compose exec -T backend python`):
   ```python
   import json, urllib.request as u
   TP = "00-a1b2c3d4e5f60718a1b2c3d4e5f60718-1111111111111111-01"
   req = u.Request("http://backend:8080/api/v1/chat/stream",
                   data=json.dumps({"query": "ขั้นตอนการจดจำนองที่ดิน…"}).encode(),
                   headers={"content-type": "application/json", "traceparent": TP},
                   method="POST")
   for line in u.urlopen(req, timeout=150):
       pass  # drain the SSE stream to completion
   ```
   Use a question that routes to an API agency so agent-proxy is exercised
   (e.g. land transfer / mortgage → กรมที่ดิน).

2. Look the trace up in Jaeger (query API is under the `/jaeger` base path):
   ```
   GET http://jaeger:16686/jaeger/api/traces/a1b2c3d4e5f60718a1b2c3d4e5f60718
   ```

## Interpreting results
- **One trace id, spans from BOTH `backend` and `agent-proxy`** → unified. Expect
  `chat_stream_endpoint`, `onechat_call`, `POST /mcp/`, `tools/call list_agency`
  (backend) and `Handle HTTP Request` (agent-proxy) all under the one id.
  (Last verified run: 82 spans, `{backend, agent-proxy}`.)
- **Multiple trace ids** → the URL context isn't surviving a hop. Check that
  `MCP_ENDPOINT_URL` has no stray query, that the `/mcp` mount is wrapped in
  `QueryTraceparentASGI`, and that agent-proxy's query-fallback extraction is present.

## Fallback correlation
Independent of trace unification, every service stamps `conversation_id` as a span
tag, so fragments can always be joined by tag in Jaeger if the URL path ever breaks.

## Probe seam
`TRACE_URL_PROBE` (backend setting, default empty) appends an extra query param to
the agent-proxy callback URL, and agent-proxy records its inbound query as the
`proxy.incoming_query` span attribute — used to re-confirm OneChat's URL-query
preservation if needed.
