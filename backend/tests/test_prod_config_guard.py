import pytest

from app.config import Settings, assert_production_config


def test_production_wildcard_cors_raises():
    s = Settings(ENV="production", CORS_ORIGINS=["*"])
    with pytest.raises(RuntimeError):
        assert_production_config(s)


def test_production_explicit_origin_does_not_raise():
    s = Settings(ENV="production", CORS_ORIGINS=["https://example.com"])
    assert_production_config(s) is None


def test_development_wildcard_cors_does_not_raise():
    s = Settings(ENV="development", CORS_ORIGINS=["*"])
    assert_production_config(s) is None
