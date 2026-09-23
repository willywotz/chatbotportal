"""Signing-key lifecycle: thumbprint kid, cache, env override, DB generation."""
import pytest

from app.features.identity.oidc import keys
from app.core.config import settings


@pytest.fixture(autouse=True)
def _clean_cache():
    keys.reset_cache()
    yield
    keys.reset_cache()


def _fresh_pem() -> str:
    return keys._generate_pem()


def test_compute_kid_is_deterministic_and_thumbprint_based():
    pem = _fresh_pem()
    jwk = keys._public_jwk_from_pem(pem)
    assert keys.compute_kid(jwk) == keys.compute_kid(jwk)
    other = keys._public_jwk_from_pem(_fresh_pem())
    assert keys.compute_kid(jwk) != keys.compute_kid(other)


def test_public_jwk_has_rs256_sig_use():
    jwk = keys._public_jwk_from_pem(_fresh_pem())
    assert jwk["alg"] == "RS256"
    assert jwk["use"] == "sig"
    assert jwk["kty"] == "RSA"


def test_register_populates_active_and_jwks():
    pem = _fresh_pem()
    jwk = keys._public_jwk_from_pem(pem)
    kid = keys.compute_kid(jwk)
    keys._register(kid, pem, jwk, active=True)

    assert keys.active_signing() == (kid, pem)
    assert keys.jwk_for_kid(kid)["kid"] == kid
    assert keys.public_jwks()["keys"][0]["kid"] == kid


def test_active_signing_raises_when_empty():
    with pytest.raises(keys.NoSigningKey):
        keys.active_signing()


async def test_ensure_signing_key_uses_env_override(monkeypatch):
    pem = _fresh_pem()
    monkeypatch.setattr(settings, "OIDC_PRIVATE_KEY", pem)
    await keys.ensure_signing_key()
    kid, active_pem = keys.active_signing()
    assert active_pem == pem
    assert keys.jwk_for_kid(kid) is not None


async def test_ensure_signing_key_generates_and_persists(_engine):
    monkey_pem = ""
    settings.OIDC_PRIVATE_KEY = monkey_pem
    from sqlalchemy import text

    try:
        await keys.ensure_signing_key()
        kid, pem = keys.active_signing()
        assert kid and "PRIVATE KEY" in pem
        assert keys.jwk_for_kid(kid) is not None

        # A second call is a no-op: same key, not a fresh generation.
        first_kid = kid
        keys.reset_cache()
        await keys.ensure_signing_key()
        assert keys.active_signing()[0] == first_kid
    finally:
        async with _engine.begin() as conn:
            await conn.execute(text("DELETE FROM signing_keys"))
