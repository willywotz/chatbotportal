import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_KID = "test-key"


@pytest.fixture(scope="session")
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public_jwk.update({"kid": _KID, "alg": "RS256", "use": "sig"})
    return private_pem, public_jwk


@pytest.fixture
def make_token(rsa_keypair):
    private_pem, _ = rsa_keypair

    def _make(scopes=(), *, role="user", sub=None, email="u@example.com",
              aud="backend", exp_delta=300, kid=_KID):
        now = int(time.time())
        claims = {
            "iss": "http://keycloak:8080/realms/chatbotportal",
            "aud": aud,
            "sub": sub or str(uuid.uuid4()),
            "email": email,
            "preferred_username": email,
            "iat": now,
            "exp": now + exp_delta,
            "realm_access": {"roles": [role]},
            "resource_access": {"backend": {"roles": list(scopes)}},
        }
        return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})

    return _make


@pytest.fixture(autouse=True)
def patch_jwks(rsa_keypair, monkeypatch):
    from app.auth import keycloak
    _, public_jwk = rsa_keypair
    monkeypatch.setattr(keycloak, "_jwk_for_kid", lambda kid: public_jwk)
