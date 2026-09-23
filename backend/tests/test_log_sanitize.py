from app.core.log_sanitize import sanitize_body, sanitize_headers


def test_truncates_long_bodies():
    out = sanitize_body("x" * 10_000, max_chars=100)
    assert len(out) <= 100 + len("…[truncated]") and out.endswith("…[truncated]")


def test_short_body_unchanged():
    assert sanitize_body("hello", max_chars=100) == "hello"


def test_none_becomes_empty():
    assert sanitize_body(None) == ""


def test_redacts_auth_headers():
    out = sanitize_headers({"Authorization": "Bearer s3cret", "X-Api-Key": "k", "accept": "json"})
    assert out["Authorization"] == "[REDACTED]" and out["X-Api-Key"] == "[REDACTED]"
    assert out["accept"] == "json"
