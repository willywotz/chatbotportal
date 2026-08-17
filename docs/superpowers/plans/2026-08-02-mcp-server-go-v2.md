# Standalone Go MCP Server (`/mcp-v2`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a standalone Go microservice that serves the AI Chatbot Portal's MCP surface (`list_agency` tool + `agencies://list` resource) over streamable-HTTP at a new `/mcp-v2` route, in parallel with the existing Python `/mcp`.

**Architecture:** A new top-level `mcp-server/` Go service mirroring `agent-proxy/`. It reads Postgres directly via `pgx` (no backend imports), reproduces the Python server's auth + redaction + agent-proxy URL rewriting + payload templating, and exposes them through the official `modelcontextprotocol/go-sdk` v1.7.0 `StreamableHTTPHandler` in stateless mode. Deployment is purely additive: one new compose service + one nginx location; the Python `/mcp` is untouched.

**Tech Stack:** Go 1.26, `github.com/modelcontextprotocol/go-sdk` v1.7.0, `github.com/jackc/pgx/v5`, OpenTelemetry (OTLP/gRPC → Jaeger), Docker Compose, nginx.

## Global Constraints

- Go module path: `github.com/willywotz/thai-citizen-guide/mcp-server`.
- MCP SDK pinned to `github.com/modelcontextprotocol/go-sdk v1.7.0`.
- **Strict MCP protocol `2026-07-28`** (SDK's `latestProtocolVersion`). `initialize` MUST negotiate `2026-07-28`; advertise only `tools` + `resources`; negotiate **no** extensions; do not emit SEP-2577-deprecated field shapes.
- Transport: streamable-HTTP, `StreamableHTTPOptions{Stateless: true}` (POST only; GET/DELETE → 405).
- Listens on `:8080`, `GET /health` returns 200. OTel service name `"mcp-server"`, exporter `jaeger:4317` insecure.
- DB access is raw SQL via `pgx` only — **no** ORM, **no** import of any `backend/` code.
- API-key hash MUST equal Python `hashlib.sha256(raw.encode()).hexdigest()`.
- `is_admin` ⇔ `users.role == "admin"`. `UserAPIKey.is_usable()` ⇔ `revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())`.
- TDD mandatory: write failing test → confirm fail → minimal code → confirm pass → commit. Prefix shell commands with `rtk`.
- Go style: Uber Go style guide.
- The Python `/mcp` server, `backend/`, `agent-proxy/`, and `mcp_discovery.py` are **not** modified.

---

## File Structure

All files under new dir `mcp-server/`:

| File | Responsibility |
|------|----------------|
| `go.mod`, `go.sum` | Module + pinned deps. |
| `auth.go` | `hashAPIKey`, `parseBearerToken`. |
| `url.go` | `externalScheme`, `traceparentQuery`, `agentProxyEndpoint`. |
| `store.go` | `Agency` type, `getAgencies`, `Identity` type, `authenticateAPIKey`. |
| `agencies.go` | `AgencyOut` type, `buildAgencyOutput` (redaction, URL rewrite, templating). |
| `mcpserver.go` | `newMCPServer`, `list_agency` tool, `agencies://list` resource. |
| `main.go` | pgxpool + tracer wiring, streamable handler mount at `/mcp-v2`, `/health`, `ListenAndServe`. |
| `util.go` | `uuidV7`, `now`, Bangkok TZ (copied from `agent-proxy/util.go`). |
| `tracer.go` | `initTracer` (copied from `agent-proxy/main.go`). |
| `Dockerfile` | Multi-stage Go build (mirror `agent-proxy/Dockerfile`). |
| `*_test.go` | Per-unit tests. |

Modified (additive) outside `mcp-server/`:
- `docker-compose.yaml` — add `mcp-server` service + two named volumes.
- `nginx/routes.conf` — add `location ^~ /mcp-v2`.
- `CONTEXT.md` — append dated entry.

---

## Task 1: Module scaffold + API-key hashing + bearer parsing

**Files:**
- Create: `mcp-server/go.mod`, `mcp-server/util.go`, `mcp-server/tracer.go`, `mcp-server/auth.go`
- Test: `mcp-server/auth_test.go`

**Interfaces:**
- Produces: `hashAPIKey(raw string) string`; `parseBearerToken(h http.Header) string`; plus `uuidV7() (string, error)`, `now() time.Time` (copied verbatim from `agent-proxy/util.go`), `initTracer(ctx) (*sdktrace.TracerProvider, error)` (copied from `agent-proxy/main.go`, service name changed to `"mcp-server"`).

- [ ] **Step 1: Scaffold module and copy shared helpers**

```bash
mkdir -p mcp-server
cd mcp-server && go mod init github.com/willywotz/thai-citizen-guide/mcp-server
```

Copy `agent-proxy/util.go` → `mcp-server/util.go` verbatim (gives `uuidV7`, `now`, `bangkokLoc`).
Copy `initTracer` from `agent-proxy/main.go` into a new `mcp-server/tracer.go` (same imports), changing only `semconv.ServiceNameKey.String("agent-proxy")` → `"mcp-server"`.

- [ ] **Step 2: Write the failing test**

```go
// mcp-server/auth_test.go
package main

import (
	"net/http"
	"testing"
)

func TestHashAPIKey_MatchesPythonSHA256Hex(t *testing.T) {
	// echo -n "tcg_example" | sha256sum
	const raw = "tcg_example"
	const want = "0d2a2f7f0f6a2b6f9c2f0b9f4a2a7f9d0e6c3b1a8d5e2c9f6b3a0d7e4c1b8a5f"
	// NOTE: replace `want` with the real digest produced by:
	//   printf '%s' 'tcg_example' | sha256sum
	got := hashAPIKey(raw)
	if len(got) != 64 {
		t.Fatalf("hash length = %d, want 64 hex chars", len(got))
	}
	_ = want
}

func TestParseBearerToken(t *testing.T) {
	h := http.Header{"Authorization": []string{"Bearer tcg_abc"}}
	if got := parseBearerToken(h); got != "tcg_abc" {
		t.Fatalf("parseBearerToken = %q, want tcg_abc", got)
	}
	if got := parseBearerToken(http.Header{}); got != "" {
		t.Fatalf("missing header should yield empty, got %q", got)
	}
}
```

Before running, compute the real digest and replace `want`:
```bash
printf '%s' 'tcg_example' | sha256sum
```
Then assert `got == want` in the test (remove the `_ = want` line).

- [ ] **Step 3: Run test to verify it fails**

Run: `cd mcp-server && rtk go test -run 'TestHashAPIKey|TestParseBearer' ./...`
Expected: FAIL — `undefined: hashAPIKey`, `undefined: parseBearerToken`.

- [ ] **Step 4: Write minimal implementation**

```go
// mcp-server/auth.go
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"strings"
)

// hashAPIKey matches Python hashlib.sha256(raw.encode()).hexdigest().
func hashAPIKey(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}

// parseBearerToken returns the token from an "Authorization: Bearer <t>" header,
// or "" when absent. Mirrors the Python split(" ")[-1] fallback semantics.
func parseBearerToken(h http.Header) string {
	v := h.Get("Authorization")
	if v == "" {
		return ""
	}
	parts := strings.Fields(v)
	return parts[len(parts)-1]
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd mcp-server && rtk go test -run 'TestHashAPIKey|TestParseBearer' ./...`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add mcp-server/go.mod mcp-server/util.go mcp-server/tracer.go mcp-server/auth.go mcp-server/auth_test.go
rtk git commit -m "feat(mcp-server): scaffold module with api-key hashing"
```

---

## Task 2: External scheme + traceparent query + agent-proxy endpoint

**Files:**
- Create: `mcp-server/url.go`
- Test: `mcp-server/url_test.go`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces:
  - `externalScheme(h http.Header) string`
  - `traceparentQuery(ctx context.Context) string` — returns `"traceparent=00-..."` (plus `&tracestate=` when present), or `""`.
  - `agentProxyEndpoint(ctx context.Context, h http.Header, agencyID string) string`

- [ ] **Step 1: Write the failing test**

```go
// mcp-server/url_test.go
package main

import (
	"context"
	"net/http"
	"strings"
	"testing"
)

func TestExternalScheme_CFVisitorWins(t *testing.T) {
	h := http.Header{
		"Cf-Visitor":        []string{`{"scheme":"https"}`},
		"X-Forwarded-Proto": []string{"http"},
	}
	if got := externalScheme(h); got != "https" {
		t.Fatalf("externalScheme = %q, want https", got)
	}
}

func TestExternalScheme_ForwardedProtoFallback(t *testing.T) {
	h := http.Header{"X-Forwarded-Proto": []string{"https"}}
	if got := externalScheme(h); got != "https" {
		t.Fatalf("externalScheme = %q, want https", got)
	}
}

func TestExternalScheme_DefaultHTTP(t *testing.T) {
	if got := externalScheme(http.Header{}); got != "http" {
		t.Fatalf("externalScheme = %q, want http", got)
	}
}

func TestAgentProxyEndpoint_BuildsURL(t *testing.T) {
	h := http.Header{
		"Cf-Visitor":      []string{`{"scheme":"https"}`},
		"X-Forwarded-Host": []string{"chatbotportal.opdc.ai.in.th"},
	}
	got := agentProxyEndpoint(context.Background(), h, "abc-123")
	want := "https://chatbotportal.opdc.ai.in.th/agent-proxy/abc-123"
	if got != want {
		t.Fatalf("agentProxyEndpoint = %q, want %q", got, want)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp-server && rtk go test -run 'TestExternalScheme|TestAgentProxyEndpoint' ./...`
Expected: FAIL — undefined functions.

- [ ] **Step 3: Write minimal implementation**

```go
// mcp-server/url.go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"

	"go.opentelemetry.io/otel/trace"
)

// externalScheme resolves the browser-facing scheme: cf-visitor JSON scheme,
// then X-Forwarded-Proto, then "http". Mirrors _external_scheme in server.py.
func externalScheme(h http.Header) string {
	if cv := h.Get("Cf-Visitor"); cv != "" {
		var m struct {
			Scheme string `json:"scheme"`
		}
		if err := json.Unmarshal([]byte(cv), &m); err == nil && m.Scheme != "" {
			return m.Scheme
		}
	}
	if p := h.Get("X-Forwarded-Proto"); p != "" {
		return p
	}
	return "http"
}

// traceparentQuery renders the active W3C context as query params, or "".
// Port of trace_util.with_trace_query.
func traceparentQuery(ctx context.Context) string {
	sc := trace.SpanContextFromContext(ctx)
	if !sc.IsValid() {
		return ""
	}
	q := url.Values{}
	q.Set("traceparent", fmt.Sprintf("00-%s-%s-%02x",
		sc.TraceID(), sc.SpanID(), byte(sc.TraceFlags())))
	if ts := sc.TraceState().String(); ts != "" {
		q.Set("tracestate", ts)
	}
	return q.Encode()
}

// agentProxyEndpoint builds the OneChat callback URL, tagged with TRACE_URL_PROBE
// (if set) and the active traceparent. Mirrors _agent_proxy_endpoint in server.py.
func agentProxyEndpoint(ctx context.Context, h http.Header, agencyID string) string {
	u := fmt.Sprintf("%s://%s/agent-proxy/%s",
		externalScheme(h), h.Get("X-Forwarded-Host"), agencyID)
	if probe := os.Getenv("TRACE_URL_PROBE"); probe != "" {
		sep := "?"
		if hasQuery(u) {
			sep = "&"
		}
		u += sep + probe
	}
	if tp := traceparentQuery(ctx); tp != "" {
		sep := "?"
		if hasQuery(u) {
			sep = "&"
		}
		u += sep + tp
	}
	return u
}

func hasQuery(u string) bool {
	for i := 0; i < len(u); i++ {
		if u[i] == '?' {
			return true
		}
	}
	return false
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp-server && rtk go test -run 'TestExternalScheme|TestAgentProxyEndpoint' ./...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add mcp-server/url.go mcp-server/url_test.go
rtk git commit -m "feat(mcp-server): external scheme + agent-proxy url building"
```

---

## Task 3: Postgres store — agencies + API-key authentication

**Files:**
- Create: `mcp-server/store.go`
- Test: `mcp-server/store_test.go`

**Interfaces:**
- Consumes: `hashAPIKey` (Task 1).
- Produces:
  - `type Agency struct` with fields: `ID, Name, Status, Description, ConnectionType string`; `DataScope []string`; `EndpointURL string`; `ExpectedPayload map[string]any`; `APIHeaders []map[string]any`.
  - `getAgencies(ctx context.Context, pool *pgxpool.Pool) ([]Agency, error)`
  - `type Identity struct { UserID string; IsAdmin bool }`
  - `authenticateAPIKey(ctx context.Context, pool *pgxpool.Pool, keyHash string) (Identity, bool, error)` — `false` when no usable key/active user; bumps `last_used_at`.

- [ ] **Step 1: Write the failing test** (mirrors `agent-proxy/store_test.go`; skips without DB)

```go
// mcp-server/store_test.go
package main

import (
	"context"
	"os"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

func testPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		t.Skip("DATABASE_URL not set")
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func TestGetAgencies_ReturnsSlice(t *testing.T) {
	pool := testPool(t)
	got, err := getAgencies(context.Background(), pool)
	if err != nil {
		t.Fatalf("getAgencies: %v", err)
	}
	for _, a := range got {
		if a.ID == "" {
			t.Fatalf("agency with empty id: %+v", a)
		}
	}
}

func TestAuthenticateAPIKey_BogusKey(t *testing.T) {
	pool := testPool(t)
	_, ok, err := authenticateAPIKey(context.Background(), pool, hashAPIKey("tcg_totallybogus"))
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if ok {
		t.Fatalf("bogus key should not authenticate")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp-server && rtk go test -run 'TestGetAgencies|TestAuthenticateAPIKey' ./...`
Expected: FAIL — undefined `getAgencies`, `authenticateAPIKey`, `Identity`.

- [ ] **Step 3: Write minimal implementation**

```go
// mcp-server/store.go
package main

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Agency struct {
	ID              string
	Name            string
	Status          string
	Description     string
	ConnectionType  string
	DataScope       []string
	EndpointURL     string
	ExpectedPayload map[string]any
	APIHeaders      []map[string]any
}

func getAgencies(ctx context.Context, pool *pgxpool.Pool) ([]Agency, error) {
	const q = `select id, name, status, description, connection_type,
	                  data_scope, endpoint_url, expected_payload, api_headers
	           from agencies`
	rows, err := pool.Query(ctx, q)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Agency
	for rows.Next() {
		var a Agency
		if err := rows.Scan(&a.ID, &a.Name, &a.Status, &a.Description,
			&a.ConnectionType, &a.DataScope, &a.EndpointURL,
			&a.ExpectedPayload, &a.APIHeaders); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

type Identity struct {
	UserID  string
	IsAdmin bool
}

// authenticateAPIKey resolves a usable API key to an active user and bumps
// last_used_at. Mirrors AuthMiddleware + UserAPIKey.is_usable() in server.py.
func authenticateAPIKey(ctx context.Context, pool *pgxpool.Pool, keyHash string) (Identity, bool, error) {
	const q = `
	    select u.id, u.role
	    from user_api_keys k
	    join users u on u.id = k.user_id
	    where k.key_hash = $1
	      and k.revoked_at is null
	      and (k.expires_at is null or k.expires_at > now())
	      and u.is_active = true
	    limit 1`
	var id, role string
	err := pool.QueryRow(ctx, q, keyHash).Scan(&id, &role)
	if errors.Is(err, pgx.ErrNoRows) {
		return Identity{}, false, nil
	}
	if err != nil {
		return Identity{}, false, err
	}
	_, _ = pool.Exec(ctx,
		`update user_api_keys set last_used_at = now() where key_hash = $1`, keyHash)
	return Identity{UserID: id, IsAdmin: role == "admin"}, true, nil
}
```

- [ ] **Step 4: Add pgx dependency and run tests**

```bash
cd mcp-server && rtk go get github.com/jackc/pgx/v5@v5.9.2 && rtk go mod tidy
rtk go test -run 'TestGetAgencies|TestAuthenticateAPIKey' ./...
```
Expected: PASS (or SKIP if `DATABASE_URL` unset — acceptable; run once with a dev DB to confirm PASS).

- [ ] **Step 5: Commit**

```bash
rtk git add mcp-server/store.go mcp-server/store_test.go mcp-server/go.mod mcp-server/go.sum
rtk git commit -m "feat(mcp-server): postgres store for agencies + api-key auth"
```

---

## Task 4: Agency output shaping — redaction, URL rewrite, templating

**Files:**
- Create: `mcp-server/agencies.go`
- Test: `mcp-server/agencies_test.go`

**Interfaces:**
- Consumes: `Agency`, `Identity` (Task 3); `agentProxyEndpoint` (Task 2).
- Produces:
  - `type AgencyOut struct` (JSON-tagged, key order matches Python: `id, name, status, description, connection_type, data_scope, endpoint_url, expected_payload, api_headers`).
  - `buildAgencyOutput(ctx context.Context, h http.Header, agencies []Agency, id Identity, userID, conversationID string) []AgencyOut`

Behavior ported from `_fetch_agencies`:
1. `api_headers` nil → `[]`.
2. Non-admin: drop every header whose `name` (case-insensitive) == `authorization`.
   (The Python deletes during enumeration — a latent skip bug; implement the *intended* full removal via filtering.)
3. `connection_type == "API"` → `endpoint_url = agentProxyEndpoint(...)`.
4. For each **top-level** string value in `expected_payload`, replace `__user_id__`→`userID`, `__conversation_id__`→`conversationID` (nested values untouched, matching Python).

- [ ] **Step 1: Write the failing test**

```go
// mcp-server/agencies_test.go
package main

import (
	"context"
	"net/http"
	"testing"
)

func sampleAgencies() []Agency {
	return []Agency{{
		ID: "a1", Name: "DOPA", Status: "active", Description: "d",
		ConnectionType: "API", DataScope: []string{"x"},
		EndpointURL: "http://origin/x",
		ExpectedPayload: map[string]any{
			"query": "{q}", "session_id": "__conversation_id__", "uid": "__user_id__",
		},
		APIHeaders: []map[string]any{
			{"name": "Authorization", "value": "secret"},
			{"name": "X-Env", "value": "prod"},
		},
	}}
}

func TestBuildOutput_NonAdminStripsAuthHeader(t *testing.T) {
	h := http.Header{"X-Forwarded-Host": []string{"host"}, "Cf-Visitor": []string{`{"scheme":"https"}`}}
	out := buildAgencyOutput(context.Background(), h, sampleAgencies(),
		Identity{UserID: "u1", IsAdmin: false}, "u1", "c1")
	for _, hd := range out[0].APIHeaders {
		if v, _ := hd["name"].(string); v == "Authorization" {
			t.Fatalf("non-admin must not see Authorization header")
		}
	}
}

func TestBuildOutput_AdminKeepsAuthHeader(t *testing.T) {
	h := http.Header{"X-Forwarded-Host": []string{"host"}}
	out := buildAgencyOutput(context.Background(), h, sampleAgencies(),
		Identity{UserID: "u1", IsAdmin: true}, "u1", "c1")
	found := false
	for _, hd := range out[0].APIHeaders {
		if v, _ := hd["name"].(string); v == "Authorization" {
			found = true
		}
	}
	if !found {
		t.Fatalf("admin should retain Authorization header")
	}
}

func TestBuildOutput_RewritesAPIEndpointAndTemplates(t *testing.T) {
	h := http.Header{"X-Forwarded-Host": []string{"host"}, "Cf-Visitor": []string{`{"scheme":"https"}`}}
	out := buildAgencyOutput(context.Background(), h, sampleAgencies(),
		Identity{UserID: "u1", IsAdmin: true}, "u1", "c1")
	if out[0].EndpointURL != "https://host/agent-proxy/a1" {
		t.Fatalf("endpoint not rewritten: %q", out[0].EndpointURL)
	}
	if out[0].ExpectedPayload["session_id"] != "c1" {
		t.Fatalf("conversation_id not templated: %v", out[0].ExpectedPayload["session_id"])
	}
	if out[0].ExpectedPayload["uid"] != "u1" {
		t.Fatalf("user_id not templated: %v", out[0].ExpectedPayload["uid"])
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp-server && rtk go test -run 'TestBuildOutput' ./...`
Expected: FAIL — undefined `buildAgencyOutput`, `AgencyOut`.

- [ ] **Step 3: Write minimal implementation**

```go
// mcp-server/agencies.go
package main

import (
	"context"
	"net/http"
	"strings"
)

type AgencyOut struct {
	ID              string           `json:"id"`
	Name            string           `json:"name"`
	Status          string           `json:"status"`
	Description     string           `json:"description"`
	ConnectionType  string           `json:"connection_type"`
	DataScope       []string         `json:"data_scope"`
	EndpointURL     string           `json:"endpoint_url"`
	ExpectedPayload map[string]any   `json:"expected_payload"`
	APIHeaders      []map[string]any `json:"api_headers"`
}

func buildAgencyOutput(ctx context.Context, h http.Header, agencies []Agency, id Identity, userID, conversationID string) []AgencyOut {
	out := make([]AgencyOut, 0, len(agencies))
	for _, a := range agencies {
		headers := a.APIHeaders
		if headers == nil {
			headers = []map[string]any{}
		}
		if !id.IsAdmin {
			kept := headers[:0:0]
			for _, hd := range headers {
				name, _ := hd["name"].(string)
				if strings.ToLower(name) == "authorization" {
					continue
				}
				kept = append(kept, hd)
			}
			headers = kept
		}

		endpoint := a.EndpointURL
		if a.ConnectionType == "API" {
			endpoint = agentProxyEndpoint(ctx, h, a.ID)
		}

		payload := make(map[string]any, len(a.ExpectedPayload))
		for k, v := range a.ExpectedPayload {
			if s, ok := v.(string); ok {
				s = strings.ReplaceAll(s, "__user_id__", userID)
				s = strings.ReplaceAll(s, "__conversation_id__", conversationID)
				payload[k] = s
				continue
			}
			payload[k] = v
		}

		out = append(out, AgencyOut{
			ID: a.ID, Name: a.Name, Status: a.Status, Description: a.Description,
			ConnectionType: a.ConnectionType, DataScope: a.DataScope,
			EndpointURL: endpoint, ExpectedPayload: payload, APIHeaders: headers,
		})
	}
	return out
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp-server && rtk go test -run 'TestBuildOutput' ./...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add mcp-server/agencies.go mcp-server/agencies_test.go
rtk git commit -m "feat(mcp-server): agency output redaction, url rewrite, templating"
```

---

## Task 5: MCP server assembly — tool, resource, conformance

**Files:**
- Create: `mcp-server/mcpserver.go`
- Test: `mcp-server/mcpserver_test.go`

**Interfaces:**
- Consumes: everything above (`getAgencies`, `authenticateAPIKey`, `buildAgencyOutput`, `parseBearerToken`, `uuidV7`).
- Produces:
  - `newMCPServer(pool *pgxpool.Pool) *mcp.Server`
  - `newStreamableHandler(srv *mcp.Server) http.Handler` — `NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return srv }, &mcp.StreamableHTTPOptions{Stateless: true})`
  - `resolveRequest(ctx, pool, h) (id Identity, userID, conversationID string, err error)` — shared by tool + resource: hashes bearer token, authenticates (anonymous when empty/unauthenticated), always mints a `conversationID` via `uuidV7`, `userID = id.UserID or uuidV7()`.

Tool: `list_agency`, no input, output `{agencies, total}`. Resource: `agencies://list`, MIME `application/json`, body = indented JSON array of the same agencies. Both read `req.Extra.Header`.

- [ ] **Step 1: Write the failing test** (raw `initialize` handshake asserts strict conformance)

```go
// mcp-server/mcpserver_test.go
package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestInitialize_Negotiates20260728AndCapabilities(t *testing.T) {
	srv := newMCPServer(nil) // nil pool: initialize does not touch the DB
	ts := httptest.NewServer(newStreamableHandler(srv))
	defer ts.Close()

	body := `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{` +
		`"protocolVersion":"2026-07-28","capabilities":{},` +
		`"clientInfo":{"name":"test","version":"0"}}}`
	req, _ := http.NewRequest(http.MethodPost, ts.URL, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	defer resp.Body.Close()
	buf := new(strings.Builder)
	_, _ = buf.ReadFrom(resp.Body)
	got := buf.String()

	if !strings.Contains(got, `"protocolVersion":"2026-07-28"`) {
		t.Fatalf("expected 2026-07-28 negotiation, got: %s", got)
	}
	if !strings.Contains(got, `"tools"`) || !strings.Contains(got, `"resources"`) {
		t.Fatalf("expected tools+resources capabilities, got: %s", got)
	}
	if strings.Contains(got, `"prompts"`) {
		t.Fatalf("must not advertise prompts capability, got: %s", got)
	}
}

func TestStatelessRejectsGET(t *testing.T) {
	srv := newMCPServer(nil)
	ts := httptest.NewServer(newStreamableHandler(srv))
	defer ts.Close()
	resp, err := http.Get(ts.URL)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("stateless GET status = %d, want 405", resp.StatusCode)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp-server && rtk go test -run 'TestInitialize|TestStateless' ./...`
Expected: FAIL — undefined `newMCPServer`, `newStreamableHandler`.

- [ ] **Step 3: Write minimal implementation**

```go
// mcp-server/mcpserver.go
package main

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const instructions = "This server exposes Thai government agency data for the AI " +
	"Chatbot Portal. Available tool:\n- list_agency: Returns a JSON object with an " +
	"`agencies` array and `total` count. Always call list_agency before answering " +
	"questions about available agencies. Never fabricate agency data."

type listAgencyOut struct {
	Agencies []AgencyOut `json:"agencies"`
	Total    int         `json:"total"`
}

func newMCPServer(pool *pgxpool.Pool) *mcp.Server {
	srv := mcp.NewServer(&mcp.Implementation{
		Name: "AI Chatbot Portal MCP", Version: "2",
	}, &mcp.ServerOptions{Instructions: instructions})

	mcp.AddTool(srv, &mcp.Tool{
		Name:        "list_agency",
		Description: "Return a JSON array of all active government agencies.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, _ struct{}) (*mcp.CallToolResult, listAgencyOut, error) {
		agencies, err := loadShaped(ctx, pool, req.Extra.Header)
		if err != nil {
			return nil, listAgencyOut{}, err
		}
		return nil, listAgencyOut{Agencies: agencies, Total: len(agencies)}, nil
	})

	srv.AddResource(&mcp.Resource{
		URI: "agencies://list", Name: "agencies", MIMEType: "application/json",
	}, func(ctx context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
		agencies, err := loadShaped(ctx, pool, req.Extra.Header)
		if err != nil {
			return nil, err
		}
		b, err := json.MarshalIndent(agencies, "", "  ")
		if err != nil {
			return nil, err
		}
		return &mcp.ReadResourceResult{Contents: []*mcp.ResourceContents{{
			URI: "agencies://list", MIMEType: "application/json", Text: string(b),
		}}}, nil
	})

	return srv
}

func newStreamableHandler(srv *mcp.Server) http.Handler {
	return mcp.NewStreamableHTTPHandler(
		func(*http.Request) *mcp.Server { return srv },
		&mcp.StreamableHTTPOptions{Stateless: true},
	)
}

// loadShaped resolves identity from headers and returns the shaped agency list.
func loadShaped(ctx context.Context, pool *pgxpool.Pool, h http.Header) ([]AgencyOut, error) {
	id, userID, conversationID, err := resolveRequest(ctx, pool, h)
	if err != nil {
		return nil, err
	}
	agencies, err := getAgencies(ctx, pool)
	if err != nil {
		return nil, err
	}
	return buildAgencyOutput(ctx, h, agencies, id, userID, conversationID), nil
}

func resolveRequest(ctx context.Context, pool *pgxpool.Pool, h http.Header) (Identity, string, string, error) {
	conversationID, err := uuidV7()
	if err != nil {
		return Identity{}, "", "", err
	}
	var id Identity
	if token := parseBearerToken(h); token != "" && token != "anonymous" && pool != nil {
		resolved, ok, aerr := authenticateAPIKey(ctx, pool, hashAPIKey(token))
		if aerr != nil {
			return Identity{}, "", "", aerr
		}
		if ok {
			id = resolved
		}
	}
	userID := id.UserID
	if userID == "" {
		if userID, err = uuidV7(); err != nil {
			return Identity{}, "", "", err
		}
	}
	return id, userID, conversationID, nil
}
```

- [ ] **Step 4: Add the SDK dependency and run tests**

```bash
cd mcp-server && rtk go get github.com/modelcontextprotocol/go-sdk@v1.7.0 && rtk go mod tidy
rtk go test -run 'TestInitialize|TestStateless' ./...
```
Expected: PASS. If field names differ (e.g. `ServerOptions.Instructions`, `Resource.MIMEType`, `ResourceContents.Text`), correct them against `go doc github.com/modelcontextprotocol/go-sdk/mcp.<Type>` — the shapes were verified present in v1.7.0; only exact casing may need a nudge.

- [ ] **Step 5: Commit**

```bash
rtk git add mcp-server/mcpserver.go mcp-server/mcpserver_test.go mcp-server/go.mod mcp-server/go.sum
rtk git commit -m "feat(mcp-server): assemble server, list_agency tool, agencies resource"
```

---

## Task 6: Main entrypoint — pool, tracer, HTTP, health

**Files:**
- Create: `mcp-server/main.go`
- Test: (covered by `mcpserver_test.go` handler tests; add a health assertion here)
- Test: `mcp-server/main_test.go`

**Interfaces:**
- Consumes: `newMCPServer`, `newStreamableHandler`, `initTracer`.
- Produces: `newRouter(srv *mcp.Server) *http.ServeMux` (mounts `/mcp-v2` + `/health`), and `main()`.

- [ ] **Step 1: Write the failing test**

```go
// mcp-server/main_test.go
package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHealthEndpoint(t *testing.T) {
	ts := httptest.NewServer(newRouter(newMCPServer(nil)))
	defer ts.Close()
	resp, err := http.Get(ts.URL + "/health")
	if err != nil {
		t.Fatalf("get health: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("health status = %d, want 200", resp.StatusCode)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp-server && rtk go test -run TestHealthEndpoint ./...`
Expected: FAIL — undefined `newRouter`.

- [ ] **Step 3: Write minimal implementation**

```go
// mcp-server/main.go
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func newRouter(srv *mcp.Server) *http.ServeMux {
	mux := http.NewServeMux()
	mux.Handle("/mcp-v2", newStreamableHandler(srv))
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"healthy","service":"mcp-server"}`))
	})
	return mux
}

func main() {
	ctx := context.Background()

	cfg := mustPanic(pgxpool.ParseConfig(os.Getenv("DATABASE_URL")))
	cfg.AfterConnect = func(ctx context.Context, conn *pgx.Conn) error {
		_, err := conn.Exec(ctx, "SET TIMEZONE TO 'Asia/Bangkok'")
		return err
	}
	pool := mustPanic(pgxpool.NewWithConfig(ctx, cfg))
	defer pool.Close()

	tp, err := initTracer(ctx)
	if err != nil {
		slog.Error("init tracer", slog.Any("error", err))
		return
	}
	defer func() { _ = tp.Shutdown(ctx) }()

	slog.Info("mcp-server listening on :8080 at /mcp-v2")
	if err := http.ListenAndServe(":8080", newRouter(newMCPServer(pool))); err != nil {
		slog.Error("http server", slog.Any("error", err))
		os.Exit(1)
	}
}

func mustPanic[T any](v T, err error) T {
	if err != nil {
		panic(err)
	}
	return v
}
```

- [ ] **Step 4: Run tests + build**

```bash
cd mcp-server && rtk go test ./... && rtk go build ./...
```
Expected: all tests PASS (DB tests SKIP without `DATABASE_URL`), build succeeds.

- [ ] **Step 5: Commit**

```bash
rtk git add mcp-server/main.go mcp-server/main_test.go
rtk git commit -m "feat(mcp-server): main entrypoint with health + /mcp-v2 mount"
```

---

## Task 7: Dockerfile

**Files:**
- Create: `mcp-server/Dockerfile`, `mcp-server/.dockerignore`

- [ ] **Step 1: Write the Dockerfile** (mirror `agent-proxy/Dockerfile`, binary name `mcp-server`)

```dockerfile
from golang:1.26-alpine as base
workdir /app
env GOPATH=/go
env GOCACHE=/root/.cache/go-build
copy go.mod go.sum ./
run --mount=type=cache,target=/go/pkg/mod \
    go mod download

from base as development
copy . .
cmd ["go", "run", "."]

from base as builder
copy . .
run --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /app/mcp-server .

from alpine as production
workdir /app
run apk --no-cache add ca-certificates tzdata wget
copy --from=builder /app/mcp-server /usr/local/bin/mcp-server
entrypoint ["/usr/local/bin/mcp-server"]
```

`.dockerignore`:
```
*_test.go
```

- [ ] **Step 2: Build the image to verify**

Run: `rtk docker build -t mcp-server-test ./mcp-server`
Expected: image builds successfully.

- [ ] **Step 3: Commit**

```bash
rtk git add mcp-server/Dockerfile mcp-server/.dockerignore
rtk git commit -m "chore(mcp-server): multi-stage dockerfile"
```

---

## Task 8: Docker Compose service

**Files:**
- Modify: `docker-compose.yaml` (add `mcp-server` service after the `agent-proxy` block; add two named volumes).

- [ ] **Step 1: Add the service** (insert after the `agent-proxy` service block)

```yaml
  mcp-server:
    build:
      context: ./mcp-server
      target: production
    restart: unless-stopped
    environment:
      DATABASE_URL: postgres://${POSTGRES_USER:-chatbot}:${POSTGRES_PASSWORD:-chatbot_secret}@${POSTGRES_HOST:-postgres}:5432/${POSTGRES_DB:-chatbot}
      TRACE_URL_PROBE: ${TRACE_URL_PROBE:-}
    depends_on:
      postgres:
        condition: service_healthy
        restart: true
      postgres-init:
        condition: service_completed_successfully
        restart: true
      jaeger:
        condition: service_started
    networks:
      - chatbot-network
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/health"]
      interval: 15s
      timeout: 10s
      retries: 3
      start_period: 20s
    volumes:
      - mcp-server-go-modules:/go/pkg/mod
      - mcp-server-go-build-cache:/root/.cache/go-build
```

Add to the top-level `volumes:` block:
```yaml
  mcp-server-go-modules:
  mcp-server-go-build-cache:
```

- [ ] **Step 2: Validate compose config**

Run: `rtk docker compose config -q`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
rtk git add docker-compose.yaml
rtk git commit -m "chore: add mcp-server service to docker compose"
```

---

## Task 9: nginx route for `/mcp-v2`

**Files:**
- Modify: `nginx/routes.conf` (add a `location ^~ /mcp-v2` block; update the header comment).

- [ ] **Step 1: Add the location block** (insert before the `location ~ ^/(api|sse|...)` regex block so intent is clear; `^~` guarantees prefix precedence over the regex regardless of order)

```nginx
location ^~ /mcp-v2 {
    proxy_pass         http://mcp-server:8080;
    proxy_http_version 1.1;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-Host $http_host;
    proxy_set_header   X-Forwarded-Proto $scheme;

    proxy_buffering    off;
    proxy_cache        off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
}
```

Update the top-of-file comment to add: `#   /mcp-v2 -> mcp-server:8080`.

- [ ] **Step 2: Validate nginx config** (via the compose nginx image)

Run: `rtk docker compose run --rm --no-deps --entrypoint 'nginx -t' nginx`
Expected: `syntax is ok` / `test is successful`. (If the entrypoint differs, validate after `docker compose up` with `docker compose exec nginx nginx -t`.)

- [ ] **Step 3: Commit**

```bash
rtk git add nginx/routes.conf
rtk git commit -m "chore(nginx): route /mcp-v2 to mcp-server"
```

---

## Task 10: Integration parity check + CONTEXT.md + finalize

**Files:**
- Modify: `CONTEXT.md` (append dated entry per project rule).

- [ ] **Step 1: Bring the stack up and smoke-test both endpoints**

```bash
rtk docker compose up -d --build mcp-server nginx
rtk docker compose ps
```

- [ ] **Step 2: Parity check `/mcp` vs `/mcp-v2`** using the Python client pattern (`backend/app/mcp/client.py`) — call `list_agency` on both and diff the `agencies` arrays (order-insensitive). They read the same DB, so `id/name/connection_type/data_scope` MUST match; `endpoint_url` for `API` agencies MUST both be the `/agent-proxy/{id}` form.

Run (from a host with `fastmcp` available, e.g. the backend venv):
```bash
rtk docker compose exec backend python -c "import asyncio; from fastmcp import Client
async def go():
    async with Client('http://mcp-server:8080/mcp-v2') as c:
        print(await c.call_tool('list_agency'))
asyncio.run(go())"
```
Expected: a `{agencies, total}` result equivalent to `/mcp`.

- [ ] **Step 3: Append CONTEXT.md entry**

Add a `## 2026-08-02 — Standalone Go MCP server at /mcp-v2` section summarizing: new `mcp-server/` service, go-sdk v1.7.0, strict MCP 2026-07-28, direct-Postgres, additive deploy, parity-verified against `/mcp`.

- [ ] **Step 4: Commit**

```bash
rtk git add CONTEXT.md
rtk git commit -m "docs: record standalone Go MCP server (/mcp-v2)"
```

- [ ] **Step 5: Full test sweep**

Run: `cd mcp-server && rtk go test ./... && rtk go vet ./...`
Expected: PASS / clean.

---

## Self-Review Notes

- **Spec coverage:** every spec section maps to a task — data boundary/direct-Postgres (T3), auth+redaction+rewrite+templating (T1/T2/T4), conformance 2026-07-28 + capabilities + stateless (T5), file layout (all), deployment additive compose+nginx (T8/T9), TDD tests mirroring the Python suite (T1–T6), parity check (T10). `mcp_discovery.py` and Python `/mcp` untouched (no task modifies them).
- **Type consistency:** `Agency`/`Identity` (T3) consumed unchanged by T4; `AgencyOut` (T4) consumed by T5; `newMCPServer`/`newStreamableHandler` (T5) consumed by T6. `req.Extra.Header` used in T5 handlers (verified `RequestExtra.Header http.Header` at go-sdk v1.7.0 `shared.go:603`, populated `streamable.go:1553`).
- **Known SDK-casing risk:** exact field names (`ServerOptions.Instructions`, `Resource.MIMEType`, `ResourceContents.Text`, `Implementation.Version`) verified present as types; Task 5 Step 4 includes a `go doc` fallback if casing differs.
