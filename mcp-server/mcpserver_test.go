package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// TestInitialize_Negotiates20260728AndCapabilities connects with the SDK's
// own client, which performs the SEP-2575 "server/discover" handshake for
// protocol version 2026-07-28 (a raw "initialize" RPC only ever negotiates
// down to the legacy 2025-11-25 version, per the SDK's negotiatedVersion).
func TestInitialize_Negotiates20260728AndCapabilities(t *testing.T) {
	srv := newMCPServer(nil) // nil pool: initialize does not touch the DB
	ts := httptest.NewServer(newStreamableHandler(srv))
	defer ts.Close()

	client := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "0"}, nil)
	transport := &mcp.StreamableClientTransport{Endpoint: ts.URL}
	cs, err := client.Connect(context.Background(), transport, nil)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	defer cs.Close()

	res := cs.InitializeResult()
	if res == nil {
		t.Fatal("InitializeResult is nil")
	}
	if res.ProtocolVersion != "2026-07-28" {
		t.Fatalf("protocolVersion = %q, want 2026-07-28", res.ProtocolVersion)
	}
	if res.Capabilities == nil || res.Capabilities.Tools == nil {
		t.Fatalf("expected tools capability, got: %+v", res.Capabilities)
	}
	if res.Capabilities.Resources == nil {
		t.Fatalf("expected resources capability, got: %+v", res.Capabilities)
	}
	if res.Capabilities.Prompts != nil {
		t.Fatalf("must not advertise prompts capability, got: %+v", res.Capabilities)
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
