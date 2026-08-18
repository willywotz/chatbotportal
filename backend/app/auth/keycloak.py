"""Keycloak OIDC token verification. Stateless: verifies against cached JWKS."""
from __future__ import annotations

from dataclasses import dataclass

import httpx
import jwt
from cachetools import TTLCache

from app.config import settings

_ALGORITHMS = ["RS256"]
_jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)


class InvalidToken(Exception):
    """The presented token failed verification."""


@dataclass(frozen=True)
class Principal:
    id: str
    email: str | None
    display_name: str | None
    role: str
    scopes: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _fetch_jwks() -> list[dict]:
    resp = httpx.get(settings.keycloak_jwks_url, timeout=5)
    resp.raise_for_status()
    return resp.json()["keys"]


def _jwk_for_kid(kid: str) -> dict:
    keys = _jwks_cache.get("keys")
    if keys is None:
        keys = _fetch_jwks()
        _jwks_cache["keys"] = keys
    for key in keys:
        if key["kid"] == kid:
            return key
    # Unknown kid: force a refresh once (key rotation).
    keys = _fetch_jwks()
    _jwks_cache["keys"] = keys
    for key in keys:
        if key["kid"] == kid:
            return key
    raise InvalidToken("unknown signing key")


def principal_from_claims(claims: dict) -> Principal:
    role = "user"
    for candidate in ("admin", "staff", "user"):
        if candidate in claims.get("realm_access", {}).get("roles", []):
            role = candidate
            break
    scopes = claims.get("resource_access", {}).get("backend", {}).get("roles", [])
    return Principal(
        id=claims["sub"],
        email=claims.get("email"),
        display_name=claims.get("name") or claims.get("preferred_username"),
        role=role,
        scopes=frozenset(scopes),
    )


def verify_token(token: str) -> Principal:
    try:
        header = jwt.get_unverified_header(token)
        jwk = _jwk_for_kid(header["kid"])
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
        claims = jwt.decode(
            token,
            public_key,
            algorithms=_ALGORITHMS,
            audience=settings.KEYCLOAK_AUDIENCE,
            issuer=settings.keycloak_issuer,
        )
    except InvalidToken:
        raise
    except Exception as exc:  # jwt.* errors, key errors
        raise InvalidToken(str(exc)) from exc
    return principal_from_claims(claims)
