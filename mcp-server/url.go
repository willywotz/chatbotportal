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
