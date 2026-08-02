package main

import (
	"net/http"
	"testing"
)

func TestHashAPIKey_MatchesPythonSHA256Hex(t *testing.T) {
	// printf '%s' 'tcg_example' | sha256sum
	const raw = "tcg_example"
	const want = "cfd95feb9c45127d328008064b4983d976d185e06d75259e64b378170c66609f"
	got := hashAPIKey(raw)
	if len(got) != 64 {
		t.Fatalf("hash length = %d, want 64 hex chars", len(got))
	}
	if got != want {
		t.Fatalf("hashAPIKey(%q) = %q, want %q", raw, got, want)
	}
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
