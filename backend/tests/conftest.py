"""
Shared pytest fixtures.

`db` spins up an in-memory SQLite database with the app's Tortoise models so
tests that exercise real queries (e.g. admin-count guardrails) run without a
live PostgreSQL instance. SQLite is sufficient: the User model uses only
portable field types (UUID/Char/Boolean/Datetime).
"""

import time
import uuid

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from tortoise import Tortoise

from app.auth.dependencies import get_current_user
from app.auth.keycloak import Principal

_KID = "test-key"

_ALL_SCOPES = frozenset({
    "agency:list", "agency:read", "agency:write", "conversation:read:own",
    "conversation:read:all", "conversation:write:own", "message:rate", "dashboard:read",
    "executive:read", "executive:write", "health:read", "usage:read", "analytics:read",
    "feedback:read", "feedback:read:detail", "audit:read", "connlog:read", "llm:read",
    "llm:write", "settings:read", "settings:write", "popular:read", "popular:write", "user:manage",
})


@pytest.fixture
def as_principal():
    """Override get_current_user with a fake Principal. Defaults to admin+all scopes.

    Returns a callable so a test can pin narrower scopes/role for denial cases.
    Import the FastAPI `app` lazily inside the test to install the override.
    """
    from app.main import app
    installed = {"app": app}

    def _install(*, scopes=_ALL_SCOPES, role="admin",
                 sub="00000000-0000-0000-0000-000000000001", email="admin@example.com"):
        p = Principal(id=sub, email=email, display_name="Admin", role=role,
                      scopes=frozenset(scopes))
        installed["app"].dependency_overrides[get_current_user] = lambda: p
        return p

    yield _install
    installed["app"].dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture(scope="function")
async def db():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["app.models"]},
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


@pytest_asyncio.fixture(autouse=True)
async def _reset_usage_context():
    from app.services.usage_context import current_user_id
    ut = current_user_id.set(None)
    try:
        yield
    finally:
        current_user_id.reset(ut)


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
