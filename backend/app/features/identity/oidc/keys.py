"""RS256 signing-key lifecycle for the OIDC provider.

The active private key signs tokens; every published public key verifies them.
Keys are generated once and persisted (shared across uvicorn workers), or taken
from the OIDC_PRIVATE_KEY env override. Public keys are held in a module-level
cache so per-request verification never touches the database — the same
trade-off the old Keycloak JWKS cache made, except the keys are ours."""
from __future__ import annotations

import hashlib
import json

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text

from app.core.config import settings

# Populated by load_into_cache()/ensure_signing_key() at startup.
_active_kid: str | None = None
_private_pem_by_kid: dict[str, str] = {}
_public_jwk_by_kid: dict[str, dict] = {}

# Dedicated 64-bit advisory-lock key so concurrent workers generate exactly one
# key on first boot (distinct from the migration lock key in app.core.db).
_KEY_LOCK = 728123456790


class NoSigningKey(RuntimeError):
    """No active signing key is loaded — startup did not run ensure_signing_key."""


def compute_kid(public_jwk: dict) -> str:
    """RFC 7638 JWK thumbprint (SHA-256, hex, first 32 chars) — stable per key."""
    canonical = json.dumps(
        {"e": public_jwk["e"], "kty": public_jwk["kty"], "n": public_jwk["n"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()[:32]


def _public_jwk_from_pem(private_pem: str) -> dict:
    private_key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"alg": "RS256", "use": "sig"})
    return jwk


def _generate_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")


def _register(kid: str, private_pem: str, public_jwk: dict, *, active: bool) -> None:
    global _active_kid
    _private_pem_by_kid[kid] = private_pem
    _public_jwk_by_kid[kid] = {**public_jwk, "kid": kid}
    if active:
        _active_kid = kid


def reset_cache() -> None:
    """Test hook — drop all cached keys."""
    global _active_kid
    _active_kid = None
    _private_pem_by_kid.clear()
    _public_jwk_by_kid.clear()


async def ensure_signing_key(session_factory=None) -> None:
    """Load or create the active signing key, then fill the in-memory cache.

    Idempotent and safe under concurrent workers: generation is serialized by a
    Postgres advisory lock and re-checks the table after acquiring it."""
    from app.core.db import AsyncSessionLocal, engine
    from app.features.identity.repositories import signing_key as key_repo

    session_factory = session_factory or AsyncSessionLocal

    if settings.OIDC_PRIVATE_KEY.strip():
        pem = settings.OIDC_PRIVATE_KEY
        public_jwk = _public_jwk_from_pem(pem)
        _register(compute_kid(public_jwk), pem, public_jwk, active=True)
        return

    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _KEY_LOCK})
        try:
            async with session_factory() as session, session.begin():
                active = await key_repo.get_active(session)
                if active is None:
                    pem = _generate_pem()
                    public_jwk = _public_jwk_from_pem(pem)
                    kid = compute_kid(public_jwk)
                    await key_repo.create(session, kid=kid, private_pem=pem, public_jwk=public_jwk)
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _KEY_LOCK})

    await load_into_cache(session_factory)


async def load_into_cache(session_factory=None) -> None:
    from app.core.db import AsyncSessionLocal
    from app.features.identity.repositories import signing_key as key_repo

    session_factory = session_factory or AsyncSessionLocal
    async with session_factory() as session:
        rows = await key_repo.all_keys(session)
        active = await key_repo.get_active(session)
        active_kid = active.kid if active else None
    for row in rows:
        _register(row.kid, row.private_pem, row.public_jwk, active=(row.kid == active_kid))


def active_signing() -> tuple[str, str]:
    """(kid, private_pem) of the current signing key."""
    if _active_kid is None:
        raise NoSigningKey("no active signing key loaded")
    return _active_kid, _private_pem_by_kid[_active_kid]


def jwk_for_kid(kid: str) -> dict | None:
    return _public_jwk_by_kid.get(kid)


def public_jwks() -> dict:
    return {"keys": list(_public_jwk_by_kid.values())}
