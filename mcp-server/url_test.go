package main

import (
	"context"
	"net/http"
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
		"Cf-Visitor":       []string{`{"scheme":"https"}`},
		"X-Forwarded-Host": []string{"chatbotportal.opdc.ai.in.th"},
	}
	got := agentProxyEndpoint(context.Background(), h, "abc-123")
	want := "https://chatbotportal.opdc.ai.in.th/agent-proxy/abc-123"
	if got != want {
		t.Fatalf("agentProxyEndpoint = %q, want %q", got, want)
	}
}
