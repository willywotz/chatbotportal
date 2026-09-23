"""RS256 access-token verification maps flat role/scope claims onto a Principal."""
import time

import jwt
import pytest

from app.auth.oidc.tokens import verify_token
from app.auth.principal import InvalidToken, Principal
from app.config import settings


def test_valid_token_yields_principal(make_token):
    p = verify_token(make_token(scopes=["agency:list"], role="user", email="a@b.co"))
    assert isinstance(p, Principal)
    assert p.role == "user"
    assert "agency:list" in p.scopes
    assert p.email == "a@b.co"
    assert p.is_admin is False


def test_admin_role_sets_is_admin(make_token):
    assert verify_token(make_token(role="admin")).is_admin is True


def test_wrong_audience_rejected(make_token):
    with pytest.raises(InvalidToken):
        verify_token(make_token(aud="someone-else"))


def test_wrong_issuer_rejected(make_token):
    with pytest.raises(InvalidToken):
        verify_token(make_token(iss="https://evil.example/oidc"))


def test_expired_token_rejected(make_token):
    with pytest.raises(InvalidToken):
        verify_token(make_token(exp_delta=-10))


def test_bad_signature_rejected(make_token):
    tok = make_token()
    with pytest.raises(InvalidToken):
        verify_token(tok[:-3] + ("aaa" if not tok.endswith("aaa") else "bbb"))


def test_unknown_kid_rejected(make_token):
    with pytest.raises(InvalidToken):
        verify_token(make_token(kid="no-such-kid"))


def test_missing_sub_rejected(rsa_keypair):
    private_pem, _ = rsa_keypair
    now = int(time.time())
    claims = {
        "iss": settings.OIDC_ISSUER,
        "aud": settings.OIDC_ISSUER,
        "email": "u@example.com",
        "name": "u@example.com",
        "iat": now,
        "exp": now + 300,
        "role": "user",
        "scope": "",
    }
    tok = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-key"})
    with pytest.raises(InvalidToken):
        verify_token(tok)
