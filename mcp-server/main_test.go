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

func TestMCPTrailingSlashRoutes(t *testing.T) {
	ts := httptest.NewServer(newRouter(newMCPServer(nil)))
	defer ts.Close()
	resp, err := http.Get(ts.URL + "/mcp-v2/")
	if err != nil {
		t.Fatalf("get /mcp-v2/: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		t.Fatalf("/mcp-v2/ status = 404, want route to match (e.g. 405 from handler)")
	}
}
