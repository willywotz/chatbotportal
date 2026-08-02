package main

import (
	"net/http"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
)

// withTracing extracts the inbound W3C trace context and runs the request
// under a server span, so handlers see a valid active SpanContext. This is
// what makes traceparentQuery (url.go) able to propagate tracing into
// agent-proxy callback URLs, and lets resolveRequest tag the span with
// conversation_id. Mirrors the middleware pattern in agent-proxy/handler.go.
func withTracing(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx := otel.GetTextMapPropagator().Extract(r.Context(), propagation.HeaderCarrier(r.Header))
		ctx, span := otel.Tracer("mcp-server").Start(ctx, "mcp-v2")
		defer span.End()
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}
