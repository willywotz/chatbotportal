import openai
import pytest
from app.features.llm.services import providers
from app.features.llm.services.errors import LlmError


def test_openai_registered():
    assert "openai" in providers.known_kinds()
    spec = providers.get("openai")
    assert spec.model_provider == "openai"


def test_unknown_kind_raises_config():
    with pytest.raises(LlmError) as e:
        providers.get("nope")
    assert e.value.kind == "config"


def test_duplicate_registration_raises():
    spec = providers.get("openai")
    with pytest.raises(ValueError):
        providers.register(spec)


def test_openai_map_error_rate_limit():
    spec = providers.get("openai")
    exc = openai.RateLimitError.__new__(openai.RateLimitError)
    assert spec.map_error(exc).kind == "rate_limited"


def test_openai_map_error_timeout():
    spec = providers.get("openai")
    exc = openai.APITimeoutError.__new__(openai.APITimeoutError)
    assert spec.map_error(exc).kind == "timeout"


def test_openai_map_error_unmapped_returns_none():
    spec = providers.get("openai")
    assert spec.map_error(RuntimeError("x")) is None
