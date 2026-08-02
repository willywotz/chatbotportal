package main

import (
	"strings"
	"testing"
)

// TestMarshalIndentNoHTMLEscape_LeavesHTMLCharsLiteral mirrors Python's
// json.dumps(..., ensure_ascii=False): <, >, & must not be escaped.
func TestMarshalIndentNoHTMLEscape_LeavesHTMLCharsLiteral(t *testing.T) {
	in := []map[string]string{{"name": "A&B <Ministry> \"Test\""}}
	b, err := marshalIndentNoHTMLEscape(in)
	if err != nil {
		t.Fatalf("marshalIndentNoHTMLEscape: %v", err)
	}
	got := string(b)
	for _, want := range []string{"<Ministry>", "A&B"} {
		if !strings.Contains(got, want) {
			t.Fatalf("output = %q, want literal %q (HTML-escaping should be disabled)", got, want)
		}
	}
	for _, escapeSeq := range []string{`\u003c`, `\u003e`, `\u0026`} {
		if strings.Contains(got, escapeSeq) {
			t.Fatalf("output = %q, contains HTML-escape sequence %q, want literal chars", got, escapeSeq)
		}
	}
	if !strings.HasPrefix(got, "[\n  {") {
		t.Fatalf("output = %q, want 2-space indented JSON array", got)
	}
}
