package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

// TestWithTracing_PropagatesTraceparent proves the middleware makes the
// inbound W3C trace context live on the request path: a handler downstream
// of withTracing must see a valid SpanContext, and traceparentQuery (used to
// tag agent-proxy callback URLs) must carry the propagated trace ID forward.
func TestWithTracing_PropagatesTraceparent(t *testing.T) {
	// Mirrors the propagator initTracer (tracer.go) installs globally in main().
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, propagation.Baggage{}))

	const inboundTraceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

	var capturedCtx context.Context
	next := http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		capturedCtx = r.Context()
	})

	req := httptest.NewRequest(http.MethodPost, "/mcp-v2", nil)
	req.Header.Set("traceparent", inboundTraceparent)
	rec := httptest.NewRecorder()

	withTracing(next).ServeHTTP(rec, req)

	sc := trace.SpanContextFromContext(capturedCtx)
	if !sc.IsValid() {
		t.Fatalf("SpanContext from downstream ctx is invalid; withTracing did not propagate the inbound traceparent")
	}

	q := traceparentQuery(capturedCtx)
	if q == "" {
		t.Fatalf("traceparentQuery = %q, want non-empty (dead trace propagation on live request path)", q)
	}
	if !strings.Contains(q, "4bf92f3577b34da6a3ce929d0e0e4736") {
		t.Fatalf("traceparentQuery = %q, want to contain propagated trace id 4bf92f3577b34da6a3ce929d0e0e4736", q)
	}
}
