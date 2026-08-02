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
