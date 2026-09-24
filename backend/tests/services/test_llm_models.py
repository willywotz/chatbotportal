from app.features.llm.models.llm_provider import LlmProvider
from app.features.llm.models.llm_binding import LlmBinding
from app.features.llm.models.llm_usage import LlmUsage


def test_provider_columns():
    cols = set(LlmProvider.__table__.columns.keys())
    assert {"provider", "model", "base_url", "api_key", "max_retries",
            "rate_limit_rps", "rate_limit_rpm", "max_queue_size", "enabled"} <= cols
    assert "auth_header" not in cols and "auth_scheme" not in cols


def test_binding_columns():
    cols = set(LlmBinding.__table__.columns.keys())
    assert {"purpose", "provider_id", "model_override",
            "timeout_override", "enabled"} <= cols
    assert "fallback_binding_id" not in cols


def test_usage_total_tokens_property():
    u = LlmUsage(model="m", purpose="brief", prompt_tokens=3, completion_tokens=4)
    assert u.total_tokens == 7
