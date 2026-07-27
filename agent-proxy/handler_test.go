package main

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace/noop"
)

func newTestHandler(load func(ctx context.Context, id string) (agency, error)) *handler {
	return &handler{
		tracer: noop.NewTracerProvider().Tracer(""),
		load:   load,
	}
}

func TestServeHTTP_MissingID(t *testing.T) {
	h := newTestHandler(func(_ context.Context, _ string) (agency, error) { return agency{}, nil })
	req := httptest.NewRequest(http.MethodPost, "/agent-proxy/", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("want %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestServeHTTP_InvalidUUIDFormat(t *testing.T) {
	h := newTestHandler(func(_ context.Context, _ string) (agency, error) { return agency{}, nil })
	req := httptest.NewRequest(http.MethodPost, "/agent-proxy/not-a-uuid", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("want %d, got %d", http.StatusBadRequest, w.Code)
	}
}

func TestServeHTTP_SuccessProxiesUpstream(t *testing.T) {
	const id = "11111111-1111-4111-8111-111111111111"

	var gotMethod, gotAuth, gotXFwd string
	var gotBody []byte
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotAuth = r.Header.Get("Authorization")
		gotXFwd = r.Header.Get("X-Forwarded-For")
		gotBody, _ = io.ReadAll(r.Body)
		w.Header().Set("X-Upstream", "yes")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"answer":"hi"}`))
	}))
	defer upstream.Close()

	h := newTestHandler(func(_ context.Context, _ string) (agency, error) {
		return agency{
			endpointURL: upstream.URL,
			apiHeaders:  []map[string]string{{"name": "Authorization", "value": "Bearer t"}},
		}, nil
	})

	req := httptest.NewRequest(http.MethodPost, "/agent-proxy/"+id, strings.NewReader(`{"query":"q"}`))
	req.Header.Set("X-Forwarded-For", "1.2.3.4")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status: want 200, got %d", w.Code)
	}
	if gotMethod != http.MethodPost {
		t.Errorf("method: want POST, got %s", gotMethod)
	}
	if gotAuth != "Bearer t" {
		t.Errorf("injected header: want Bearer t, got %q", gotAuth)
	}
	if gotXFwd != "" {
		t.Errorf("X-Forwarded-For should be stripped, got %q", gotXFwd)
	}
	if string(gotBody) != `{"query":"q"}` {
		t.Errorf("upstream body: got %q", gotBody)
	}
	if w.Body.String() != `{"answer":"hi"}` {
		t.Errorf("client body: got %q", w.Body.String())
	}
	if w.Header().Get("X-Upstream") != "yes" {
		t.Errorf("upstream response header not forwarded")
	}
}

func TestServeHTTP_PropagatesTraceContext(t *testing.T) {
	otel.SetTextMapPropagator(propagation.TraceContext{})
	tp := sdktrace.NewTracerProvider()
	defer func() { _ = tp.Shutdown(context.Background()) }()

	const id = "11111111-1111-4111-8111-111111111111"
	const traceID = "0af7651916cd43dd8448eb211c80319c"
	const inboundSpanID = "b7ad6b7169203331"

	var gotTP string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotTP = r.Header.Get("traceparent")
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	h := &handler{
		tracer: tp.Tracer("test"),
		load: func(_ context.Context, _ string) (agency, error) {
			return agency{endpointURL: upstream.URL}, nil
		},
	}

	req := httptest.NewRequest(http.MethodPost, "/agent-proxy/"+id, strings.NewReader(`{"query":"q"}`))
	req.Header.Set("traceparent", "00-"+traceID+"-"+inboundSpanID+"-01")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)

	if gotTP == "" {
		t.Fatalf("no traceparent forwarded to upstream request")
	}
	parts := strings.Split(gotTP, "-")
	if len(parts) != 4 {
		t.Fatalf("malformed upstream traceparent: %q", gotTP)
	}
	if parts[1] != traceID {
		t.Errorf("upstream trace id: want %s, got %s (inbound context not continued)", traceID, parts[1])
	}
	if parts[2] == inboundSpanID {
		t.Errorf("upstream span id still equals inbound %s: agent-proxy did not create+inject a child span (raw pass-through)", inboundSpanID)
	}
}
