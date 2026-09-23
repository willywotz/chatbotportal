"""End-to-end OIDC endpoints: discovery, JWKS, authorize, token, userinfo."""
import base64
import hashlib
from urllib.parse import parse_qs, urlparse

from app.auth.oidc.passwords import hash_password
from app.auth.oidc.tokens import verify_token
from app.config import settings
from app.models.user import UserRole
from app.repositories import user as user_repo

REDIRECT = settings.OIDC_ALLOWED_REDIRECT_URIS[0]
CLIENT = settings.OIDC_CLIENT_ID


def _pkce():
    verifier = "test-verifier-abcdefghijklmnopqrstuvwxyz-0123456789"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def _seed(session, email="oidc@example.com", password="pw123456", role=UserRole.admin):
    await user_repo.create(
        session, email=email, password_hash=hash_password(password),
        role=role, display_name="OIDC User",
    )


async def test_discovery_document(client):
    r = await client.get("/oidc/.well-known/openid-configuration")
    assert r.status_code == 200
    doc = r.json()
    assert doc["issuer"] == settings.OIDC_ISSUER
    assert doc["code_challenge_methods_supported"] == ["S256"]
    assert doc["id_token_signing_alg_values_supported"] == ["RS256"]
    assert doc["authorization_endpoint"].endswith("/authorize")


async def test_jwks_lists_public_key(client):
    r = await client.get("/oidc/.well-known/jwks.json")
    assert r.status_code == 200
    keys = r.json()["keys"]
    assert keys and keys[0]["kty"] == "RSA" and keys[0]["alg"] == "RS256"
    assert "d" not in keys[0]  # never leak the private component


async def test_authorize_get_renders_login(client):
    _, challenge = _pkce()
    r = await client.get("/oidc/authorize", params={
        "client_id": CLIENT, "redirect_uri": REDIRECT, "response_type": "code",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "xyz",
    })
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "password" in r.text


async def test_authorize_get_rejects_unknown_client(client):
    _, challenge = _pkce()
    r = await client.get("/oidc/authorize", params={
        "client_id": "someone-else", "redirect_uri": REDIRECT,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    assert r.status_code == 400


async def test_authorize_get_rejects_bad_redirect(client):
    _, challenge = _pkce()
    r = await client.get("/oidc/authorize", params={
        "client_id": CLIENT, "redirect_uri": "https://evil.example/cb",
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    assert r.status_code == 400


async def test_full_code_flow_then_userinfo(client, db_session):
    verifier, challenge = _pkce()
    await _seed(db_session)

    resp = await client.post("/oidc/authorize", data={
        "email": "oidc@example.com", "password": "pw123456",
        "client_id": CLIENT, "redirect_uri": REDIRECT, "response_type": "code",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "xyz",
    })
    assert resp.status_code == 302
    location = urlparse(resp.headers["location"])
    query = parse_qs(location.query)
    assert query["state"] == ["xyz"]
    code = query["code"][0]

    tok = await client.post("/oidc/token", data={
        "grant_type": "authorization_code", "code": code,
        "code_verifier": verifier, "redirect_uri": REDIRECT, "client_id": CLIENT,
    })
    assert tok.status_code == 200
    body = tok.json()
    assert body["token_type"] == "Bearer"
    principal = verify_token(body["access_token"])
    assert principal.role == "admin"

    info = await client.get("/oidc/userinfo", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert info.status_code == 200
    assert info.json()["email"] == "oidc@example.com"

    refreshed = await client.post("/oidc/token", data={
        "grant_type": "refresh_token", "refresh_token": body["refresh_token"], "client_id": CLIENT,
    })
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != body["refresh_token"]


async def test_authorize_post_bad_password_reshows_login(client, db_session):
    _, challenge = _pkce()
    await _seed(db_session, email="who@example.com", password="right-pw")
    resp = await client.post("/oidc/authorize", data={
        "email": "who@example.com", "password": "wrong-pw",
        "client_id": CLIENT, "redirect_uri": REDIRECT, "response_type": "code",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "xyz",
    })
    assert resp.status_code == 200
    assert "invalid email or password" in resp.text


async def test_token_rejects_unsupported_grant(client):
    r = await client.post("/oidc/token", data={"grant_type": "password", "client_id": CLIENT})
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_grant_type"


async def test_userinfo_requires_valid_token(client):
    r = await client.get("/oidc/userinfo", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
