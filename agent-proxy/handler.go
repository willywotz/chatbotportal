package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

var (
	pathRegexp = regexp.MustCompile(`^/agent-proxy/([^/]+)`)
	uuidRegexp = regexp.MustCompile(`^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$`)
)

// upstreamTimeout mirrors the backend's AGENCY_CHAT_TIMEOUT.
const upstreamTimeout = 180 * time.Second

// maxSpanBodyBytes caps request/response bodies recorded on spans and logs.
const maxSpanBodyBytes = 8 << 10

func newHTTPClient() *http.Client {
	t := http.DefaultTransport.(*http.Transport).Clone()
	t.MaxIdleConns = 100
	t.MaxIdleConnsPerHost = 100
	t.MaxConnsPerHost = 0
	return &http.Client{Timeout: upstreamTimeout, Transport: t}
}

var httpClient = newHTTPClient()

type agencyLoader func(ctx context.Context, id string) (agency, error)

type handler struct {
	pool   *pgxpool.Pool
	tracer trace.Tracer
	load   agencyLoader
}

func truncate(s string) string {
	if len(s) <= maxSpanBodyBytes {
		return s
	}
	return s[:maxSpanBodyBytes] + "…(truncated)"
}

func (h *handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	ctx := otel.GetTextMapPropagator().Extract(r.Context(), propagation.HeaderCarrier(r.Header))
	// OneChat sometimes drops headers but preserves URL query strings; fall
	// back to traceparent/tracestate query params so the trace still continues.
	if !trace.SpanContextFromContext(ctx).IsValid() {
		if tp := r.URL.Query().Get("traceparent"); tp != "" {
			carrier := propagation.MapCarrier{"traceparent": tp}
			if ts := r.URL.Query().Get("tracestate"); ts != "" {
				carrier["tracestate"] = ts
			}
			ctx = otel.GetTextMapPropagator().Extract(r.Context(), carrier)
		}
	}
	ctx, span := h.tracer.Start(ctx, "Handle HTTP Request")
	defer span.End()
	span.SetAttributes(attribute.String("proxy.incoming_query", r.URL.RawQuery))

	m := pathRegexp.FindStringSubmatch(r.URL.Path)
	if len(m) < 2 {
		span.SetStatus(codes.Error, "missing id")
		http.Error(w, "Bad Request: missing id", http.StatusBadRequest)
		return
	}
	agencyID := m[1]

	if !uuidRegexp.MatchString(agencyID) {
		span.SetStatus(codes.Error, "invalid id format")
		http.Error(w, "Bad Request: invalid id format", http.StatusBadRequest)
		return
	}

	a, err := h.load(ctx, agencyID)
	if errors.Is(err, pgx.ErrNoRows) {
		span.SetStatus(codes.Error, "agent not found or inactive")
		http.Error(w, "Not Found", http.StatusNotFound)
		return
	}
	if err != nil {
		span.SetStatus(codes.Error, "internal server error: "+err.Error())
		slog.Error("Error querying database", slog.Any("error", err))
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}

	defer func() { _ = r.Body.Close() }()
	var body bytes.Buffer
	if _, err := io.Copy(&body, r.Body); err != nil {
		span.SetStatus(codes.Error, "error reading request body: "+err.Error())
		slog.Error("Error reading request body", slog.Any("error", err))
		http.Error(w, "Bad Request", http.StatusBadRequest)
		return
	}

	req, err := http.NewRequestWithContext(ctx, r.Method, a.endpointURL, bytes.NewReader(body.Bytes()))
	if err != nil {
		span.SetStatus(codes.Error, "error building upstream request: "+err.Error())
		slog.Error("Error building upstream request", slog.Any("error", err))
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}
	req.Header = r.Header.Clone()

	span.SetAttributes(attribute.String("proxy.method", req.Method))
	span.SetAttributes(attribute.String("proxy.url", req.URL.String()))
	span.SetAttributes(attribute.String("proxy.body", truncate(body.String())))

	for _, apiHeader := range a.apiHeaders {
		req.Header.Set(apiHeader["name"], apiHeader["value"])
	}

	// collect keys first to avoid modifying map during iteration
	var toDelete []string
	for k := range req.Header {
		if strings.HasPrefix(k, "X-Forwarded") {
			toDelete = append(toDelete, k)
		}
	}
	for _, k := range toDelete {
		req.Header.Del(k)
	}
	otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(req.Header))
	for k, v := range req.Header {
		span.SetAttributes(attribute.String("proxy.request_header."+k, strings.Join(v, ",")))
	}

	startTime := time.Now()
	resp, err := httpClient.Do(req)
	latency := time.Since(startTime).Milliseconds()
	if err != nil {
		if h.pool != nil {
			_ = h.addConnectionLog(ctx, agencyID, "error", latency, "error forwarding request: "+err.Error(), body.String(), "")
		}
		span.SetStatus(codes.Error, "error forwarding request to backend: "+err.Error())
		slog.Error("Error forwarding request to backend", slog.Any("error", err))
		http.Error(w, "Bad Gateway", http.StatusBadGateway)
		return
	}
	defer func() { _ = resp.Body.Close() }()

	span.SetAttributes(attribute.Int("proxy.response_status", resp.StatusCode))
	for k, v := range resp.Header {
		w.Header()[k] = v
		span.SetAttributes(attribute.String("proxy.response_header."+k, strings.Join(v, ",")))
	}
	w.WriteHeader(resp.StatusCode)

	// Stream to the client; mirror a bounded prefix into capture for span/log.
	var capture bytes.Buffer
	limited := io.MultiWriter(w, &limitedWriter{buf: &capture, remaining: maxSpanBodyBytes})
	if _, err := io.Copy(limited, resp.Body); err != nil {
		span.SetStatus(codes.Error, "error streaming response body: "+err.Error())
		slog.Error("Error streaming response body", slog.Any("error", err))
	}
	responseBody := capture.String()

	span.SetAttributes(attribute.String("proxy.response_body", responseBody))

	var raw struct {
		Query string `json:"query"`
	}
	_ = json.Unmarshal(body.Bytes(), &raw)

	var payload map[string]any
	_ = json.Unmarshal(body.Bytes(), &payload)
	for key, placeholder := range a.expectedPayload {
		if placeholder != "__conversation_id__" {
			continue
		}
		if v, ok := payload[key]; ok {
			if id := fmt.Sprint(v); id != "" {
				span.SetAttributes(attribute.String("conversation_id", id))
			}
		}
		break
	}
	detail := fmt.Sprintf("Query: %s\n\nAnswer: %s", raw.Query, truncate(responseBody))

	status := "success"
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		status = "error"
	}

	if h.pool != nil {
		// only count successful calls
		if status == "success" {
			if err := incrementTotalCalls(ctx, h.pool, agencyID); err != nil {
				span.SetStatus(codes.Error, "error updating total_calls: "+err.Error())
				slog.Error("Error updating total_calls", slog.Any("error", err))
			}
		}

		if err := h.addConnectionLog(ctx, agencyID, status, latency, detail, body.String(), responseBody); err != nil {
			span.SetAttributes(attribute.Bool("proxy.connection_log_failed", true))
		}
	}

	if resp.StatusCode >= 500 {
		span.SetStatus(codes.Error, fmt.Sprintf("upstream returned %d", resp.StatusCode))
	} else {
		span.SetStatus(codes.Ok, "request handled successfully")
	}
}

func (h *handler) addConnectionLog(ctx context.Context, agencyID, status string, latency int64, detail, requestBody, responseBody string) error {
	ctx, span := h.tracer.Start(ctx, "Add Connection Log")
	defer span.End()

	if err := insertConnectionLog(ctx, h.pool, agencyID, status, latency, detail, requestBody, responseBody); err != nil {
		span.SetStatus(codes.Error, "error inserting connection log: "+err.Error())
		slog.Error("Error inserting connection log", slog.Any("error", err))
		return err
	}
	return nil
}

// limitedWriter writes at most remaining bytes to buf and silently drops the rest.
type limitedWriter struct {
	buf       *bytes.Buffer
	remaining int
}

func (l *limitedWriter) Write(p []byte) (int, error) {
	if l.remaining > 0 {
		n := len(p)
		if n > l.remaining {
			n = l.remaining
		}
		l.buf.Write(p[:n])
		l.remaining -= n
	}
	return len(p), nil // report full length so io.Copy/MultiWriter does not error
}
