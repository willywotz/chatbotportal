"""
Shared pytest fixtures.

`db_session` runs the app's Alembic migrations against a session-scoped
Postgres+PGroonga testcontainer, then hands each test an `AsyncSession`
bound to an outer transaction that is rolled back afterward. Nested writes
inside a test use savepoints, so a test's own commits never leak.
"""

import asyncio
import os
import time
import uuid

# This machine's docker credsStore breaks the testcontainers Ryuk sidecar pull;
# session-scoped containers are cleaned up by their context manager regardless.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.auth.dependencies import get_current_user
from app.auth.keycloak import Principal
from app.config import settings

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


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("groonga/pgroonga:4.0.8-debian-17", driver="asyncpg") as pg:
        yield pg


@pytest_asyncio.fixture(scope="session")
async def _engine(pg_container):
    from alembic import command
    from alembic.config import Config

    url = pg_container.get_connection_url()
    settings.DATABASE_URL = url  # alembic/env.py derives sqlalchemy.url from settings
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    await asyncio.to_thread(command.upgrade, cfg, "head")

    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine):
    """Outer transaction rolled back after each test; nested writes use savepoints."""
    conn = await _engine.connect()
    trans = await conn.begin()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


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
