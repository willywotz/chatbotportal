package main

import (
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"strings"
)

// hashAPIKey matches Python hashlib.sha256(raw.encode()).hexdigest().
func hashAPIKey(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}

// parseBearerToken returns the token from an "Authorization: Bearer <t>" header,
// or "" when absent. Mirrors the Python split(" ")[-1] fallback semantics.
func parseBearerToken(h http.Header) string {
	v := h.Get("Authorization")
	if v == "" {
		return ""
	}
	parts := strings.Fields(v)
	return parts[len(parts)-1]
}
