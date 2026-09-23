"""OAuth2 / OIDC grant machinery: authorization codes, PKCE, refresh rotation.

Pure service layer — no FastAPI imports. Callers own the transaction; this
module never commits. Raises OAuthError with a spec error code the router maps
to the OAuth error response shape."""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc import tokens
from app.config import settings
from app.models.user import User
from app.repositories import oauth as oauth_repo
from app.repositories import user as user_repo


class OAuthError(Exception):
    """A grant failure carrying an OAuth2 `error` code."""

    def __init__(self, error: str, description: str = ""):
        super().__init__(description or error)
        self.error = error
        self.description = description


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """S256: BASE64URL(SHA256(verifier)) == challenge (no padding)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, code_challenge)


async def issue_authorization_code(
    session: AsyncSession,
    *,
    user: User,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    scope: str,
) -> str:
    code = secrets.token_urlsafe(32)
    await oauth_repo.create_auth_code(
        session,
        code_hash=_sha256_hex(code),
        user_id=user.id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        scope=scope,
        expires_at=_now() + timedelta(seconds=settings.OIDC_CODE_TTL),
    )
    return code


def _token_response(user: User, refresh_token: str) -> dict:
    access = tokens.mint_access_token(
        sub=str(user.id), email=user.email, display_name=user.display_name, role=user.role.value,
    )
    id_token = tokens.mint_id_token(
        sub=str(user.id), email=user.email, display_name=user.display_name,
    )
    return {
        "access_token": access,
        "id_token": id_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.OIDC_ACCESS_TOKEN_TTL,
    }


async def _new_refresh_token(session: AsyncSession, user: User, client_id: str, scope: str) -> str:
    raw = secrets.token_urlsafe(48)
    await oauth_repo.create_refresh_token(
        session,
        token_hash=_sha256_hex(raw),
        user_id=user.id,
        client_id=client_id,
        scope=scope,
        expires_at=_now() + timedelta(seconds=settings.OIDC_REFRESH_TOKEN_TTL),
    )
    return raw


async def exchange_code(
    session: AsyncSession,
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str,
) -> dict:
    row = await oauth_repo.get_auth_code(session, _sha256_hex(code))
    if row is None or row.consumed:
        raise OAuthError("invalid_grant", "authorization code is invalid or already used")
    row.consumed = True
    await session.flush()
    if row.expires_at < _now():
        raise OAuthError("invalid_grant", "authorization code expired")
    if row.client_id != client_id:
        raise OAuthError("invalid_grant", "client mismatch")
    if row.redirect_uri != redirect_uri:
        raise OAuthError("invalid_grant", "redirect_uri mismatch")
    if not verify_pkce(code_verifier, row.code_challenge):
        raise OAuthError("invalid_grant", "PKCE verification failed")

    user = await user_repo.get(session, row.user_id)
    if user is None or not user.is_active:
        raise OAuthError("invalid_grant", "account unavailable")

    refresh = await _new_refresh_token(session, user, client_id, row.scope)
    return _token_response(user, refresh)


async def refresh(session: AsyncSession, *, refresh_token: str, client_id: str) -> dict:
    row = await oauth_repo.get_refresh_token(session, _sha256_hex(refresh_token))
    if row is None:
        raise OAuthError("invalid_grant", "unknown refresh token")
    if row.revoked:
        # Reuse of a rotated token — treat the whole chain as compromised.
        await oauth_repo.revoke_user_tokens(session, row.user_id)
        raise OAuthError("invalid_grant", "refresh token reuse detected")
    if row.expires_at < _now():
        raise OAuthError("invalid_grant", "refresh token expired")
    if row.client_id != client_id:
        raise OAuthError("invalid_grant", "client mismatch")

    user = await user_repo.get(session, row.user_id)
    if user is None or not user.is_active:
        raise OAuthError("invalid_grant", "account unavailable")

    row.revoked = True
    await session.flush()
    new_refresh = await _new_refresh_token(session, user, client_id, row.scope)
    return _token_response(user, new_refresh)
