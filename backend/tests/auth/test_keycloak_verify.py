import time

import jwt
import pytest
from app.auth.keycloak import verify_token, InvalidToken, Principal


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


def test_expired_token_rejected(make_token):
    with pytest.raises(InvalidToken):
        verify_token(make_token(exp_delta=-10))


def test_bad_signature_rejected(make_token):
    tok = make_token()
    with pytest.raises(InvalidToken):
        verify_token(tok[:-3] + ("aaa" if not tok.endswith("aaa") else "bbb"))


def test_missing_sub_rejected(rsa_keypair):
    private_pem, _ = rsa_keypair
    now = int(time.time())
    claims = {
        "iss": "http://keycloak:8080/realms/chatbotportal",
        "aud": "backend",
        "email": "u@example.com",
        "preferred_username": "u@example.com",
        "iat": now,
        "exp": now + 300,
        "realm_access": {"roles": ["user"]},
        "resource_access": {"backend": {"roles": []}},
    }
    tok = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-key"})
    with pytest.raises(InvalidToken):
        verify_token(tok)
