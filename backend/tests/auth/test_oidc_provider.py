"""Authorization-code + PKCE exchange and refresh-token rotation."""
import base64
import hashlib

import pytest

from app.auth.oidc import provider
from app.auth.oidc.tokens import verify_token
from app.config import settings
from app.models.user import UserRole
from app.repositories import user as user_repo

REDIRECT = settings.OIDC_ALLOWED_REDIRECT_URIS[0]
CLIENT = settings.OIDC_CLIENT_ID


def _pkce() -> tuple[str, str]:
    verifier = "verifier-0123456789-abcdefghijklmnop-XYZ"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def _make_user(session, *, role=UserRole.staff, email="p@example.com"):
    return await user_repo.create(
        session, email=email, password_hash="x", role=role, display_name="P",
    )


async def _issue(session, user, challenge, *, scope="openid"):
    return await provider.issue_authorization_code(
        session, user=user, client_id=CLIENT, redirect_uri=REDIRECT,
        code_challenge=challenge, scope=scope,
    )


def test_verify_pkce_s256():
    verifier, challenge = _pkce()
    assert provider.verify_pkce(verifier, challenge)
    assert not provider.verify_pkce("wrong-verifier", challenge)


async def test_authorization_code_happy_path(db_session):
    verifier, challenge = _pkce()
    user = await _make_user(db_session, role=UserRole.admin)
    code = await _issue(db_session, user, challenge)

    tokens_out = await provider.exchange_code(
        db_session, code=code, code_verifier=verifier, redirect_uri=REDIRECT, client_id=CLIENT,
    )
    assert tokens_out["token_type"] == "Bearer"
    assert tokens_out["expires_in"] == settings.OIDC_ACCESS_TOKEN_TTL
    principal = verify_token(tokens_out["access_token"])
    assert principal.id == str(user.id)
    assert principal.role == "admin"
    assert "user:manage" in principal.scopes


async def test_code_is_single_use(db_session):
    verifier, challenge = _pkce()
    user = await _make_user(db_session)
    code = await _issue(db_session, user, challenge)
    await provider.exchange_code(
        db_session, code=code, code_verifier=verifier, redirect_uri=REDIRECT, client_id=CLIENT,
    )
    with pytest.raises(provider.OAuthError):
        await provider.exchange_code(
            db_session, code=code, code_verifier=verifier, redirect_uri=REDIRECT, client_id=CLIENT,
        )


async def test_bad_verifier_rejected(db_session):
    _, challenge = _pkce()
    user = await _make_user(db_session)
    code = await _issue(db_session, user, challenge)
    with pytest.raises(provider.OAuthError):
        await provider.exchange_code(
            db_session, code=code, code_verifier="not-the-verifier", redirect_uri=REDIRECT, client_id=CLIENT,
        )


async def test_redirect_uri_mismatch_rejected(db_session):
    verifier, challenge = _pkce()
    user = await _make_user(db_session)
    code = await _issue(db_session, user, challenge)
    with pytest.raises(provider.OAuthError):
        await provider.exchange_code(
            db_session, code=code, code_verifier=verifier,
            redirect_uri="https://evil.example/callback", client_id=CLIENT,
        )


async def test_unknown_code_rejected(db_session):
    with pytest.raises(provider.OAuthError):
        await provider.exchange_code(
            db_session, code="nope", code_verifier="x", redirect_uri=REDIRECT, client_id=CLIENT,
        )


async def test_refresh_rotates_and_old_token_is_reuse_revoked(db_session):
    verifier, challenge = _pkce()
    user = await _make_user(db_session)
    code = await _issue(db_session, user, challenge)
    first = await provider.exchange_code(
        db_session, code=code, code_verifier=verifier, redirect_uri=REDIRECT, client_id=CLIENT,
    )
    original_refresh = first["refresh_token"]

    rotated = await provider.refresh(db_session, refresh_token=original_refresh, client_id=CLIENT)
    assert rotated["refresh_token"] != original_refresh
    assert verify_token(rotated["access_token"]).id == str(user.id)

    # Reusing the rotated-out token is detected and revokes the whole chain.
    with pytest.raises(provider.OAuthError):
        await provider.refresh(db_session, refresh_token=original_refresh, client_id=CLIENT)
    with pytest.raises(provider.OAuthError):
        await provider.refresh(db_session, refresh_token=rotated["refresh_token"], client_id=CLIENT)


async def test_refresh_unknown_token_rejected(db_session):
    with pytest.raises(provider.OAuthError):
        await provider.refresh(db_session, refresh_token="unknown", client_id=CLIENT)
