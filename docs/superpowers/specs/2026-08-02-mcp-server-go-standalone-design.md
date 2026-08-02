# Standalone Go MCP Server (`/mcp-v2`) — Design

**Date:** 2026-08-02
**Branch:** `feat/mcp-server-go-v2`
**Status:** Draft — awaiting user review

## Summary

Extract the FastMCP server currently embedded in the FastAPI backend
(`backend/app/mcp/`) into a standalone Go microservice, served at a **new route
`/mcp-v2`**. The existing Python `/mcp` server is **kept unchanged** and runs in
parallel. This is a purely **additive** deployment: nothing existing is removed
or modified except one new nginx location block and one new compose service.

Running side-by-side lets us diff `/mcp` vs `/mcp-v2` responses against the same
database to verify parity before trusting the new service.

## Goals

- A standalone Go service that exposes the same MCP surface as the Python server
  (`list_agency` tool + `agencies://list` resource) over streamable-HTTP.
- Clean decoupling from backend internals — the Go service imports **no** backend
  Python code. Achieved for free by rewriting in Go.
- Match the repo's existing Go-microservice pattern (`agent-proxy/`).
- Behavioral parity with the Python server (auth, redaction, URL rewriting,
  payload templating) so `/mcp` and `/mcp-v2` return equivalent data.

## Non-Goals

- Removing or modifying the existing Python `/mcp` server (kept as-is).
- Supporting the legacy SSE transport (`/sse`, `/messages`) — the old server keeps
  serving those; the new service is streamable-HTTP only.
- Touching `backend/app/services/mcp_discovery.py` — that is an **outbound** client
  for discovering agency MCP endpoints, unrelated to this server.

## Key Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Motivation | Clean decoupling | User-stated driver. |
| 2 | Language | Go | User-requested rewrite; matches `agent-proxy`. |
| 3 | Data boundary | **Direct Postgres via pgx** | Mirrors `agent-proxy` exactly; no new backend endpoint, no extra hop; enables same-DB parity checking. |
| 4 | Deployment | **Parallel, additive** at `/mcp-v2` | Keep old `/mcp`; de-risks cutover; enables A/B parity diff. |
| 5 | MCP library | `github.com/modelcontextprotocol/go-sdk` **v1.7.0** | Official SDK; latest (2026-07-27); `StreamableHTTPHandler{Stateless:true}` verified present. |
| 6 | Transport | streamable-HTTP, `Stateless: true` | Matches Python `stateless_http=True`; safe under concurrency. |
| 7 | Config source | env var | `TRACE_URL_PROBE` via env (simpler than DB-loaded settings parity). |

## Architecture

```
                          nginx/routes.conf
   /mcp, /sse, /messages ───────────────▶ backend:8080   (Python, unchanged)
   /mcp-v2              ───────────────▶ mcp-server:8080  (Go, NEW)
   /agent-proxy/        ───────────────▶ agent-proxy:8080 (existing)

   mcp-server ──pgx/SQL──▶ postgres  (same DB the backend/agent-proxy use)
   mcp-server ──OTLP────▶ jaeger:4317  (service name "mcp-server")
```

New top-level directory `mcp-server/`, Go module
`github.com/willywotz/thai-citizen-guide/mcp-server`, laid out like `agent-proxy/`.

### File responsibilities

| File | Responsibility |
|------|----------------|
| `main.go` | `pgxpool` connect (`DATABASE_URL`, `SET TIMEZONE 'Asia/Bangkok'` on connect); init OTel tracer (service `"mcp-server"` → `jaeger:4317`, W3C traceparent + baggage propagators); build `mcp.Server` via `NewServer`; register tool + resource; wrap in `NewStreamableHTTPHandler(getServer, &StreamableHTTPOptions{Stateless:true})`; auth middleware; `GET /health`; `ListenAndServe(":8080")`. |
| `store.go` | `getAgencies(ctx, pool) ([]agency, error)` — reads `id, name, status, description, connection_type, data_scope, endpoint_url, expected_payload, api_headers` from `agencies`; `authenticateAPIKey(ctx, pool, keyHash) (userID string, isAdmin bool, ok bool)` — looks up usable `user_api_keys`, joins active `users`, bumps `last_used_at`. |
| `auth.go` | `hashAPIKey(raw) string` = `sha256` hex (byte-for-byte match with Python `hashlib.sha256(raw).hexdigest()`); Bearer-token parse from `Authorization` header; anonymous fallback (`Bearer anonymous`) → random `user_id` + generated `conversation_id`. |
| `agencies.go` | Port of `_fetch_agencies`: for each agency — drop `Authorization` entry from `api_headers` unless caller is admin; if `connection_type == "API"`, rewrite `endpoint_url` to the agent-proxy callback URL; template `__user_id__` / `__conversation_id__` inside `expected_payload` string values. |
| `url.go` | `externalScheme(r)` — prefer `cf-visitor` JSON `{"scheme":...}`, then `X-Forwarded-Proto`, then request scheme; `agentProxyEndpoint(r, agencyID)` — `{scheme}://{X-Forwarded-Host}/agent-proxy/{id}`, append `TRACE_URL_PROBE` if set, then inject active W3C `traceparent` as a query param (port of `with_trace_query`). |
| `mcpserver.go` | `mcp.Server` construction, `Implementation{Name:"AI Chatbot Portal MCP", ...}` + instructions string; `list_agency` tool handler (returns `{agencies, total}`); `agencies://list` resource handler (returns indented JSON string). |
| `*_test.go` | TDD ports of the Python suite (see Testing). |
| `Dockerfile` | Multi-stage Go build, mirror `agent-proxy/Dockerfile`. |
| `go.mod` / `go.sum` | Module + pinned deps (`go-sdk@v1.7.0`, `pgx/v5`, otel stack matching `agent-proxy`). |

## Ported Business Logic (from `backend/app/mcp/server.py`)

The Go tool/resource must reproduce `_fetch_agencies` exactly:

1. **Auth resolution (middleware).** Read `Authorization: Bearer <token>`; if token
   present and not `anonymous`, `keyHash = sha256hex(token)`, look up a usable
   `user_api_keys` row + active `users` row → set `user_id`, `is_admin`, bump
   `last_used_at`. Always ensure a `conversation_id` (generate UUID if absent).
   Stash `user_id`, `is_admin`, `conversation_id` + the `*http.Request` into the
   request `context.Context` (via the `getServer` closure) so the tool handler can
   read them.
2. **Fetch** all agencies (no status filter — matches current `Agency.all()`).
3. **Header redaction.** For each agency, normalize `api_headers` (`null` → `[]`);
   if a header's `name` lowercases to `authorization` **and caller is not admin**,
   **remove** that header entry.
4. **URL rewrite.** If `connection_type == "API"`, replace `endpoint_url` with
   `agentProxyEndpoint(r, id)`.
5. **Payload templating.** For each string value in `expected_payload`, replace
   `__user_id__` → resolved user id, `__conversation_id__` → resolved conversation id.
6. **Shape.** Tool returns `{"agencies": [...], "total": N}`; resource returns the
   `agencies` array as indented, non-ASCII-escaped JSON (`ensure_ascii=False`).

Set OTel span attribute `conversation_id` on the request span (parity with Python
middleware).

## Deployment Wiring (additive only)

- **`docker-compose.yaml`** — new service `mcp-server`:
  - `build: { context: ./mcp-server }`, `restart: unless-stopped`
  - `environment: DATABASE_URL` (same as backend/agent-proxy), `TRACE_URL_PROBE` (optional)
  - `depends_on`: `postgres` (healthy), `postgres-init` (completed), `jaeger` (started)
  - `networks: [chatbot-network]`
  - `healthcheck`: `wget -q -O /dev/null http://127.0.0.1:8080/health`
  - Its own go-modules + go-build-cache named volumes (mirror `agent-proxy-go-modules` / `agent-proxy-go-build-cache`).
- **`nginx/routes.conf`** — add, without touching the existing `mcp|sse|messages`
  backend regex:
  ```nginx
  location ^~ /mcp-v2 {
      proxy_pass         http://mcp-server:8080;
      proxy_http_version 1.1;
      proxy_buffering     off;
      proxy_set_header    Host $host;
      proxy_set_header    X-Forwarded-Host $host;
      proxy_set_header    X-Forwarded-Proto $scheme;
      # (match the header set the backend /mcp location already forwards)
  }
  ```
  `^~` ensures this prefix wins over the existing `~ ^/(api|sse|messages|mcp|...)`
  regex (which would otherwise also match `/mcp-v2`).
- **Backend** — no changes.

## Testing (TDD — mandatory)

Red → green → refactor for each unit. Go tests mirror the Python suite:

| Go test | Mirrors | Asserts |
|---------|---------|---------|
| `mcpserver_test.go` | `test_mcp_streamable_calls`, `test_mcp_stateless_http` | `list_agency` over streamable-HTTP returns `{agencies,total}`; stateless POST works, GET/DELETE → 405. |
| `auth_test.go` | `test_mcp_role_access` | admin sees `Authorization` headers; non-admin has them stripped; anonymous still gets data. |
| `agencies_test.go` | `_fetch_agencies` behavior | redaction, `API`→agent-proxy rewrite, `__user_id__`/`__conversation_id__` templating. |
| `url_test.go` | `test_mcp_endpoint_scheme`, `test_trace_url_probe`, `test_mcp_trace_inbound` | `cf-visitor`/`X-Forwarded-Proto` scheme resolution; `TRACE_URL_PROBE` appended; traceparent injected. |
| `store_test.go` | — | SQL round-trips against a test Postgres (or pgx mock, following `agent-proxy/store_test.go`'s approach). |

`hashAPIKey` must have a test asserting a known raw→hash vector equals the Python
output, so auth is provably compatible.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Reading request headers inside tool handler | Use the SDK `getServer func(*http.Request)` closure to stash headers + resolved identity into the request context. **Verified present in v1.7.0.** |
| SDK API drift v1.2→v1.7 | Core symbols (`StreamableHTTPHandler`, `Stateless`, `NewServer`, `AddResource`, `AddTool`) verified at v1.7.0; confirm exact tool-handler generic signature during implementation. |
| `hashAPIKey` mismatch → auth silently fails | Known-vector unit test against Python output. |
| nginx regex vs prefix precedence | Use `location ^~ /mcp-v2` so the prefix beats the existing regex location. |
| `TRACE_URL_PROBE` parity | Sourced via env var; if DB-loaded parity is later required, add a settings read. |

## Out of Scope

- Retiring the Python `/mcp` server (future, once parity is confirmed).
- SSE transport in Go.
- Changes to `agent-proxy`, `mcp_discovery`, or the DB schema.
