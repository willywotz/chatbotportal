"""Mint and verify the provider's RS256 JWTs.

Access tokens carry a flat `role` plus space-delimited `scope`; verification
maps those straight onto a Principal. The public key is looked up from the
in-memory JWKS cache (app.auth.oidc.keys), so verification stays synchronous
and does no I/O — matching the FastAPI dependency call site."""
from __future__ import annotations

import time

import jwt

from app.auth.oidc import keys
from app.auth.principal import InvalidToken, Principal
from app.auth.scopes import scopes_for_role
from app.config import settings

_ALGORITHMS = ["RS256"]


def _now() -> int:
    return int(time.time())


def mint_access_token(*, sub: str, email: str | None, display_name: str | None, role: str) -> str:
    kid, private_pem = keys.active_signing()
    now = _now()
    scope = " ".join(sorted(scopes_for_role(role)))
    claims = {
        "iss": settings.OIDC_ISSUER,
        "aud": settings.oidc_audience,
        "sub": sub,
        "email": email,
        "name": display_name,
        "role": role,
        "scope": scope,
        "iat": now,
        "exp": now + settings.OIDC_ACCESS_TOKEN_TTL,
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})


def mint_id_token(*, sub: str, email: str | None, display_name: str | None, nonce: str | None = None) -> str:
    kid, private_pem = keys.active_signing()
    now = _now()
    claims: dict = {
        "iss": settings.OIDC_ISSUER,
        "aud": settings.OIDC_CLIENT_ID,
        "sub": sub,
        "email": email,
        "name": display_name,
        "iat": now,
        "exp": now + settings.OIDC_ACCESS_TOKEN_TTL,
    }
    if nonce:
        claims["nonce"] = nonce
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})


def principal_from_claims(claims: dict) -> Principal:
    role = claims.get("role", "user")
    scope = claims.get("scope", "")
    return Principal(
        id=claims["sub"],
        email=claims.get("email"),
        display_name=claims.get("name"),
        role=role,
        scopes=frozenset(scope.split()),
    )


def verify_token(token: str) -> Principal:
    try:
        header = jwt.get_unverified_header(token)
        jwk = keys.jwk_for_kid(header.get("kid", ""))
        if jwk is None:
            raise InvalidToken("unknown signing key")
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
        claims = jwt.decode(
            token,
            public_key,
            algorithms=_ALGORITHMS,
            audience=settings.oidc_audience,
            issuer=settings.OIDC_ISSUER,
        )
        return principal_from_claims(claims)
    except InvalidToken:
        raise
    except Exception as exc:  # jwt.* errors, key errors, malformed claims
        raise InvalidToken(str(exc)) from exc
