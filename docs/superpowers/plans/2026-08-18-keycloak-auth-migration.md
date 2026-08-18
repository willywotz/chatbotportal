# Keycloak Auth Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the backend's local password/session/API-key auth with Keycloak (OIDC), verifying a bearer token per request and enforcing authorization through Keycloak-defined scopes behind a fail-closed gate.

**Architecture:** A stateless JWKS verifier turns a Keycloak access token into a `Principal`. A fail-closed global gate (`enforce_access`) admits only the `/api/v1/public/*` namespace or a valid token. Each protected route declares a required scope via FastAPI `Security(require_scope, ...)`; Keycloak composite realm roles map role → scope. The `users`, `sessions`, and `user_api_keys` tables are dropped; rows store the Keycloak `sub` directly.

**Tech Stack:** FastAPI, Tortoise ORM + aerich, PyJWT (RS256/JWKS), httpx, cachetools, pytest + pytest-asyncio, Keycloak.

**Spec:** `docs/superpowers/specs/2026-08-18-keycloak-auth-migration-design.md`

## Global Constraints

- Clean Architecture: routers → services → repositories; verification/authz live in `app/auth/`, never in services.
- 15-Factor: all Keycloak settings come from environment variables; no secrets in git.
- TDD mandatory: failing test → confirm fail → minimal code → confirm pass → commit.
- **Migration-safe ordering invariant:** after every task the full suite passes AND no route becomes more permissive than today. The old role gate stays active until all scopes are in place (Phase 6), then is swapped for the fail-closed gate (Phase 7).
- Full English endpoint names, American English identifiers.
- Test transport: `httpx.AsyncClient` against the app; DB via the in-memory SQLite `db` fixture in `tests/conftest.py`.
- No live Keycloak in tests: tests mint their own RS256 tokens and point the verifier at a local test JWKS.

---

## Authorization matrix (source of truth for Phase 6)

Scopes are Keycloak `backend` client roles, delivered in `resource_access.backend.roles`.

| Route | Method | Scope required | user | staff | admin |
| --- | --- | --- | :-: | :-: | :-: |
| `/public/status` | GET | — (public) | ✓ | ✓ | ✓ |
| `/public/agencies` | GET | — (public) | ✓ | ✓ | ✓ |
| `/public/popular-questions` | GET | — (public) | ✓ | ✓ | ✓ |
| `/public/chat` | POST | — (public, token optional) | ✓ | ✓ | ✓ |
| `/public/agencies/{id}/logo` | GET | — (public) | ✓ | ✓ | ✓ |
| `/authentication/me` | GET | — (valid token only) | ✓ | ✓ | ✓ |
| `/agencies` | GET | `agency:list` | ✓ | ✓ | ✓ |
| `/agencies` | POST | `agency:write` | | | ✓ |
| `/agencies/{id}` | GET | `agency:read` | | | ✓ |
| `/agencies/{id}` | PUT/PATCH/DELETE | `agency:write` | | | ✓ |
| `/agencies/{id}/increment-calls` | POST | `agency:write` | | | ✓ |
| `/agencies/{id}/status` | PATCH | `agency:write` | | | ✓ |
| `/agencies/{id}/conformance` | POST | `agency:write` | | | ✓ |
| `/agencies/{id}/health/history` | GET | `agency:read` | | | ✓ |
| `/agencies/{id}/golden*` (GET) | GET | `agency:read` | | | ✓ |
| `/agencies/{id}/golden*` (POST/DELETE) | POST/DELETE | `agency:write` | | | ✓ |
| `/agencies/{id}/logo` | POST | `agency:write` | | | ✓ |
| `/agencies/mcp/discover` | POST | `agency:write` | | | ✓ |
| `/agencies/parse-specification` | POST | `agency:write` | | | ✓ |
| `/history` | GET | `conversation:read:own` | ✓ | ✓ | ✓ |
| `/history` | POST | `conversation:write:own` | ✓ | ✓ | ✓ |
| `/history/{id}` | GET | `conversation:read:own` | ✓ | ✓ | ✓ |
| `/history/{id}/messages` | GET | `conversation:read:own` | ✓ | ✓ | ✓ |
| `/history/{id}` | DELETE | `conversation:write:own` | ✓ | ✓ | ✓ |
| `/messages/{id}/rating` | PATCH | `message:rate` | ✓ | ✓ | ✓ |
| `/dashboard/statistics` | GET | `dashboard:read` | | ✓ | ✓ |
| `/executive-summary` | GET | `executive:read` | | ✓ | ✓ |
| `/executive-summary/regenerate` | POST | `executive:write` | | | ✓ |
| `/agency-health` | GET | `health:read` | | ✓ | ✓ |
| `/usage-heatmap` | GET | `usage:read` | | ✓ | ✓ |
| `/insight/usage` | GET | `usage:read` | | ✓ | ✓ |
| `/analytics-insights` | GET | `analytics:read` | | | ✓ |
| `/feedback/statistics` | GET | `feedback:read` | | ✓ | ✓ |
| `/feedback/agencies/{id}/low-rated` | GET | `feedback:read:detail` | | | ✓ |
| `/audit-log` | GET | `audit:read` | | | ✓ |
| `/connection-logs*` | GET | `connlog:read` | | | ✓ |
| `/language-model/*` | GET | `llm:read` | | | ✓ |
| `/language-model/*` | POST/PATCH/DELETE | `llm:write` | | | ✓ |
| `/settings` | GET | `settings:read` | | | ✓ |
| `/settings` | PUT | `settings:write` | | | ✓ |
| `/settings/cache/flush` | POST | `settings:write` | | | ✓ |
| `/popular-questions` (admin) | GET | `popular:read` | | | ✓ |
| `/popular-questions*` | POST/PATCH/DELETE | `popular:write` | | | ✓ |
| `/users*` | ALL | `user:manage` | | | ✓ |

**Composite realm roles (role → scope bundle):**
- `user`: `agency:list`, `conversation:read:own`, `conversation:write:own`, `message:rate`.
- `staff`: everything in `user` + `dashboard:read`, `executive:read`, `health:read`, `usage:read`, `feedback:read`.
- `admin`: every scope above (includes `user` + `staff` + all admin-only scopes) plus `conversation:read:all`.

---

## Phase 1 — Foundation: dependencies, config, Keycloak

### Task 1: Dependencies and configuration

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`

**Interfaces:**
- Produces: `settings.KEYCLOAK_URL`, `settings.KEYCLOAK_REALM`, `settings.KEYCLOAK_CLIENT_ID`, `settings.KEYCLOAK_AUDIENCE`, `settings.KEYCLOAK_ADMIN_CLIENT_ID`, `settings.KEYCLOAK_ADMIN_CLIENT_SECRET`, and derived `settings.keycloak_issuer` / `settings.keycloak_jwks_url` / `settings.keycloak_token_url`.

- [ ] **Step 1: Add PyJWT with crypto extra** to `backend/pyproject.toml` dependencies:

```toml
    "pyjwt[crypto]>=2.9.0",
```

- [ ] **Step 2: Add Keycloak settings** to `app/config.py` (`Settings` class), and remove `SESSION_*`, `SESSION_COOKIE_NAME`, `AUTH_COOKIE_SECURE`, and any API-key settings:

```python
    KEYCLOAK_URL: str = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
    KEYCLOAK_REALM: str = os.getenv("KEYCLOAK_REALM", "chatbotportal")
    KEYCLOAK_CLIENT_ID: str = os.getenv("KEYCLOAK_CLIENT_ID", "portal-spa")
    KEYCLOAK_AUDIENCE: str = os.getenv("KEYCLOAK_AUDIENCE", "backend")
    KEYCLOAK_ADMIN_CLIENT_ID: str = os.getenv("KEYCLOAK_ADMIN_CLIENT_ID", "portal-admin")
    KEYCLOAK_ADMIN_CLIENT_SECRET: str = os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET", "")

    @property
    def keycloak_issuer(self) -> str:
        return f"{self.KEYCLOAK_URL}/realms/{self.KEYCLOAK_REALM}"

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/certs"

    @property
    def keycloak_token_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/token"
```

- [ ] **Step 3: Sync and import-smoke**

Run: `cd backend && uv sync && uv run python -c "import app.config; print(app.config.settings.keycloak_jwks_url)"`
Expected: prints the JWKS URL, no import error.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/app/config.py backend/uv.lock
git commit -m "feat(auth): add Keycloak settings and PyJWT dependency"
```

### Task 2: Keycloak service and realm export

**Files:**
- Modify: `compose.yaml`
- Create: `deploy/keycloak/realm-export.json`

**Interfaces:**
- Produces: a `chatbotportal` realm with the `portal-spa` public client (PKCE), the `portal-admin` confidential client (`realm-management` roles), the `backend` client whose client-roles are the scopes in the authorization matrix, composite realm roles `user`/`staff`/`admin`, an audience mapper adding `backend` to `aud`, and one seed admin user.

- [ ] **Step 1: Add a Keycloak service** to `compose.yaml`:

```yaml
  keycloak:
    image: quay.io/keycloak/keycloak:26.0
    command: ["start-dev", "--import-realm"]
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_BOOTSTRAP_PASSWORD:-admin}
    volumes:
      - ./deploy/keycloak/realm-export.json:/opt/keycloak/data/import/realm-export.json:ro
    ports:
      - "8080:8080"
```

- [ ] **Step 2: Write `deploy/keycloak/realm-export.json`** defining, at minimum:
  - `"realm": "chatbotportal"`, `"enabled": true`.
  - `clients`: `portal-spa` (`publicClient: true`, `standardFlowEnabled: true`, PKCE `S256`, redirect URIs + web origins for the SPA); `portal-admin` (`serviceAccountsEnabled: true`, `publicClient: false`, assigned `realm-management` roles `view-users`, `manage-users`); `backend` (bearer-only, with a client role per scope in the matrix, and an audience protocol mapper adding `backend` to `aud`).
  - `roles.client.backend`: one entry per scope: `agency:list`, `agency:read`, `agency:write`, `conversation:read:own`, `conversation:read:all`, `conversation:write:own`, `message:rate`, `dashboard:read`, `executive:read`, `executive:write`, `health:read`, `usage:read`, `analytics:read`, `feedback:read`, `feedback:read:detail`, `audit:read`, `connlog:read`, `llm:read`, `llm:write`, `settings:read`, `settings:write`, `popular:read`, `popular:write`, `user:manage`.
  - `roles.realm`: composite roles `user`, `staff`, `admin` whose `composites.client.backend` list matches the role → scope bundle above.
  - `users`: one admin, `enabled: true`, realm-role `admin`, a set password (dev only).

- [ ] **Step 3: Boot Keycloak and verify the realm imports**

Run: `docker compose up -d keycloak && sleep 20 && curl -s localhost:8080/realms/chatbotportal/.well-known/openid-configuration | head -c 200`
Expected: JSON with `"issuer":".../realms/chatbotportal"`.

- [ ] **Step 4: Commit**

```bash
git add compose.yaml deploy/keycloak/realm-export.json
git commit -m "feat(auth): add Keycloak service and realm export"
```

---

## Phase 2 — Auth core: token verification and Principal

### Task 3: Test token helper (RS256 keypair + make_token)

**Files:**
- Create: `backend/tests/auth/conftest.py`

**Interfaces:**
- Produces: pytest fixtures `rsa_keypair` (private PEM + public JWK) and a factory `make_token(scopes=(), *, role="user", sub=None, email="u@example.com", aud="backend", exp_delta=300, kid="test-key")` returning a signed JWT string; a fixture `patch_jwks` that points the verifier's JWKS cache at the test public key.

- [ ] **Step 1: Write the helper** (this is test infrastructure, so it has no separate failing test; it is exercised by Task 4):

```python
import time
import uuid
import json
import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

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
```

- [ ] **Step 2: Commit** (verified by Task 4's tests):

```bash
git add backend/tests/auth/conftest.py
git commit -m "test(auth): RS256 token helper and JWKS patch fixtures"
```

### Task 4: JWKS verifier and Principal (`app/auth/keycloak.py`)

**Files:**
- Create: `backend/app/auth/keycloak.py`
- Create: `backend/tests/auth/test_keycloak_verify.py`

**Interfaces:**
- Consumes: `settings.keycloak_*`, `make_token` / `patch_jwks` (Task 3).
- Produces:
  - `class Principal` — frozen dataclass `id: str`, `email: str | None`, `display_name: str | None`, `role: str`, `scopes: frozenset[str]`, property `is_admin`.
  - `def verify_token(token: str) -> Principal` — raises `InvalidToken` on bad sig/iss/aud/exp.
  - `class InvalidToken(Exception)`.
  - `def principal_from_claims(claims: dict) -> Principal`.
  - internal `_jwk_for_kid(kid: str) -> dict` (cached JWKS lookup; patched in tests).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/auth/test_keycloak_verify.py -v`
Expected: FAIL (module `app.auth.keycloak` not found).

- [ ] **Step 3: Implement `app/auth/keycloak.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/auth/test_keycloak_verify.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/keycloak.py backend/tests/auth/test_keycloak_verify.py
git commit -m "feat(auth): stateless Keycloak JWKS token verifier and Principal"
```

---

## Phase 3 — Dependencies: Principal-backed auth + require_scope (old gate still active)

This phase swaps the *identity source* to the token but keeps the existing
`enforce_role_allowlist` behavior, so access is unchanged. It adds `require_scope`
and `Principal`-typed dependencies used by Phase 6.

### Task 5: Rewrite `app/auth/dependencies.py` (identity from token; keep old gate)

**Files:**
- Modify: `backend/app/auth/dependencies.py`
- Create: `backend/tests/auth/test_dependencies_token.py`

**Interfaces:**
- Consumes: `verify_token`, `Principal`, `InvalidToken` (Task 4).
- Produces:
  - `get_current_user_optional(request) -> Principal | None` — no `Authorization` header ⇒ `None`; present but invalid ⇒ raises 401.
  - `get_current_user(request) -> Principal` — missing/invalid ⇒ 401.
  - `require_admin(principal=Depends(get_current_user)) -> Principal` — transitional; 403 unless `principal.is_admin`.
  - `require_scope(security_scopes, request) -> Principal` — 401 if no valid token, 403 unless every required scope ∈ `principal.scopes`.
  - `_resolve_role(conn) -> str | None` — reads the bearer, returns `principal.role` or `None`; still used by the unchanged `enforce_role_allowlist` this phase.
- Note: `enforce_role_allowlist` and all `_is_*` helpers stay in this file, unchanged, for now.

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from fastapi import Depends, FastAPI, Security
from fastapi.security import SecurityScopes
from httpx import ASGITransport, AsyncClient
from app.auth.dependencies import get_current_user, require_scope
from app.auth.keycloak import Principal

def _mini_app():
    app = FastAPI()

    @app.get("/me")
    async def me(p: Principal = Depends(get_current_user)):
        return {"id": p.id, "role": p.role}

    @app.get("/needs-dashboard")
    async def needs(p: Principal = Security(require_scope, scopes=["dashboard:read"])):
        return {"ok": True}

    return app

@pytest.mark.asyncio
async def test_missing_token_is_401(make_token):
    async with AsyncClient(transport=ASGITransport(app=_mini_app()), base_url="http://t") as c:
        assert (await c.get("/me")).status_code == 401

@pytest.mark.asyncio
async def test_valid_token_ok(make_token):
    tok = make_token(role="staff")
    async with AsyncClient(transport=ASGITransport(app=_mini_app()), base_url="http://t") as c:
        r = await c.get("/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200 and r.json()["role"] == "staff"

@pytest.mark.asyncio
async def test_scope_denied_is_403(make_token):
    tok = make_token(scopes=[], role="user")
    async with AsyncClient(transport=ASGITransport(app=_mini_app()), base_url="http://t") as c:
        r = await c.get("/needs-dashboard", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403

@pytest.mark.asyncio
async def test_scope_granted_is_200(make_token):
    tok = make_token(scopes=["dashboard:read"], role="staff")
    async with AsyncClient(transport=ASGITransport(app=_mini_app()), base_url="http://t") as c:
        r = await c.get("/needs-dashboard", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/auth/test_dependencies_token.py -v`
Expected: FAIL (`require_scope` not importable / behavior differs).

- [ ] **Step 3: Replace the resolver internals** in `app/auth/dependencies.py`. Remove `_header_api_key` API-key logic, `_resolve_api_key`, `_resolve_session_user`, `_resolve_token`. Add:

```python
from fastapi import HTTPException, Request, status
from fastapi.security import SecurityScopes
from starlette.requests import HTTPConnection

from app.auth.keycloak import InvalidToken, Principal, verify_token
from app.services.usage_context import current_user_id

_invalid = HTTPException(status_code=401, detail="Invalid or expired credentials",
                         headers={"WWW-Authenticate": "Bearer"})


def _bearer(conn: HTTPConnection) -> str | None:
    auth = conn.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else None


def _principal(conn: HTTPConnection) -> Principal | None:
    token = _bearer(conn)
    if token is None:
        return None
    try:
        p = verify_token(token)
    except InvalidToken:
        raise _invalid
    current_user_id.set(p.id)
    return p


async def get_current_user_optional(request: Request) -> Principal | None:
    return _principal(request)


async def get_current_user(request: Request) -> Principal:
    p = _principal(request)
    if p is None:
        raise _invalid
    return p


async def get_current_user_non_ephemeral(request: Request) -> Principal:
    return await get_current_user(request)


async def require_admin(request: Request) -> Principal:
    p = await get_current_user(request)
    if not p.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return p


async def require_scope(
    security_scopes: SecurityScopes,
    principal: Principal = Depends(get_current_user),
) -> Principal:
    # Resolve via Depends(get_current_user) — NOT a direct call — so that
    # app.dependency_overrides[get_current_user] in tests continues to control
    # this route's identity. A direct call would bypass the override.
    missing = set(security_scopes.scopes) - principal.scopes
    if missing:
        raise HTTPException(status_code=403,
                            detail="This token lacks the required scope")
    return principal


async def _resolve_role(conn: HTTPConnection) -> str | None:
    p = _principal(conn)
    return p.role if p else None
```

Keep the existing `enforce_role_allowlist` and every `_is_*` predicate exactly as
they are (they call the new `_resolve_role`).

- [ ] **Step 3b: Add the `as_principal` fixture to the ROOT `tests/conftest.py`** — the single seam the 8 override-based tests will migrate to (Task 5b):

```python
import pytest
from app.auth.keycloak import Principal
from app.auth.dependencies import get_current_user

_ALL_SCOPES = frozenset({
    "agency:list","agency:read","agency:write","conversation:read:own",
    "conversation:read:all","conversation:write:own","message:rate","dashboard:read",
    "executive:read","executive:write","health:read","usage:read","analytics:read",
    "feedback:read","feedback:read:detail","audit:read","connlog:read","llm:read",
    "llm:write","settings:read","settings:write","popular:read","popular:write","user:manage",
})

@pytest.fixture
def as_principal():
    """Override get_current_user with a fake Principal. Defaults to admin+all scopes.
    Returns a callable so a test can pin narrower scopes/role for denial cases.
    Import the FastAPI `app` lazily inside the test to install the override."""
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
```

- [ ] **Step 4: Update the usage-context reset fixture** in `tests/conftest.py`: drop `current_api_key_id` (it no longer exists after Task 11; if referenced now, leave it until Task 11 and only remove the import there). For this task, ensure `tests/conftest.py` still imports cleanly.

- [ ] **Step 5: Run the new tests + full suite**

Run: `cd backend && uv run pytest tests/auth/test_dependencies_token.py -v && uv run pytest -q`
Expected: new tests PASS. Some legacy cookie/API-key auth tests now fail — that is expected; they are rewritten/removed in Phase 7. Record the failing set; it must only contain auth-transport tests (`test_session_cookie_auth`, `test_api_key_rest_auth`, WS auth), nothing else.

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth/dependencies.py backend/tests/auth/test_dependencies_token.py
git commit -m "feat(auth): resolve identity from Keycloak token; add require_scope"
```

### Task 5b: Centralize the override-based tests on `as_principal`

**Files:** the 8 test files that do `app.dependency_overrides[get_current_user] = ...`, plus the 2 that inject a bare `object()`. Find them with:
`grep -rl "dependency_overrides\[get_current_user\]" backend/tests` and `grep -rln "= object()" backend/tests`.

**Interfaces:** consumes `as_principal` (Task 5). After this task, no test constructs a fake `User` for auth; all use `as_principal(...)`.

- [ ] **Step 1:** For each file, replace the local `_admin()`/`_user()` fake-`User` factory and its `app.dependency_overrides[get_current_user] = _admin` install with a call to the `as_principal` fixture: `as_principal()` for an admin (all scopes), or `as_principal(scopes=[...], role="user")` where the test asserts a specific role/permission. Remove now-unused `User` imports.
- [ ] **Step 2:** Fix the two `object()`-injecting tests (`test_parse_spec_auth.py`, `test_parse_spec_endpoint.py`) the same way — they will break the moment `require_scope` reads `.scopes`, so give them a real `Principal` via `as_principal`.
- [ ] **Step 3:** Run the full suite

Run: `cd backend && OTEL_SDK_DISABLED=true uv run pytest -q -k "not (api_key or session or ws or auth_login)"`
Expected: PASS (the auth-transport tests slated for deletion in Task 17 remain the only failures).

- [ ] **Step 4: Commit** `test(auth): centralize dependency-override auth on as_principal fixture`.

---

## Phase 4 — Move anonymous routes into /public; remove chat WebSocket

### Task 6: Move guest chat to /public/chat and drop the WebSocket

**Files:**
- Modify: `backend/app/routers/chat.py`
- Modify: `backend/app/main.py`
- Delete: `backend/app/services/chat/ws.py`
- Modify: `backend/tests/` chat tests that post to `/api/v1/chat` or use the WS

**Interfaces:**
- Produces: `POST /api/v1/public/chat` (JSON + SSE), no `/api/v1/chat`, no chat WebSocket.

- [ ] **Step 1: Update the failing test** — point one existing chat test at the new path:

```python
# in the chat endpoint test module
r = await client.post("/api/v1/public/chat", json={"query": "hello"})
assert r.status_code == 200
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/test_chat_endpoint.py -q` (use the actual chat test path)
Expected: FAIL (404 at `/api/v1/public/chat`).

- [ ] **Step 3: Change the router prefix and delete the WebSocket handler** in `app/routers/chat.py`:
  - `router = APIRouter(prefix="/public/chat", tags=["Chat"])` and keep the POST at path `""`.
  - Delete the entire `@router.websocket("")` handler, `_connections`, and imports of `ConnectionRegistry`, `handle_chat_frame`, `resolve_ws_user`, `ws_origin_allowed`.
  - Delete `app/services/chat/ws.py`.

- [ ] **Step 4: Run the chat + full suite**

Run: `cd backend && uv run pytest tests/ -q -k "chat"`
Expected: PASS (WS tests removed/failing-set only). Fix any remaining references to `/api/v1/chat`.

- [ ] **Step 5: Commit**

```bash
git add -A backend/app/routers/chat.py backend/app/main.py backend/tests
git rm backend/app/services/chat/ws.py
git commit -m "refactor(chat): serve guest chat at /public/chat; drop WebSocket"
```

### Task 7: Move the agency logo GET under /public

**Files:**
- Modify: `backend/app/routers/agencies/logo.py`
- Modify: `backend/app/routers/agencies/__init__.py` (route registration order)
- Modify: logo tests

**Interfaces:**
- Produces: `GET /api/v1/public/agencies/{agency_id}/logo`. The upload `POST /agencies/{id}/logo` stays where it is (admin).

- [ ] **Step 1: Update the failing test** to fetch the logo at `/api/v1/public/agencies/{id}/logo`.

- [ ] **Step 2: Run it to confirm 404** on the old assumption.

- [ ] **Step 3: Register the logo GET on a public path.** Simplest: register it directly on the public router. In `app/routers/public_status.py` (prefix `/public`) add:

```python
from app.routers.agencies.logo import get_agency_logo
router.get("/agencies/{agency_id}/logo", summary="Get agency logo image")(get_agency_logo)
```

Remove the `@router.get("/{agency_id}/logo", ...)` registration from `agencies/logo.py` (keep the `get_agency_logo` function and the upload route).

- [ ] **Step 4: Run logo tests**

Run: `cd backend && uv run pytest -q -k "logo"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A backend/app/routers
git commit -m "refactor(agency): serve logo image under /public"
```

---

## Phase 5 — Data model: drop tables, store Keycloak sub

### Task 8: Convert conversation/message user FK to plain user_id

**Files:**
- Modify: `backend/app/models/conversation.py`
- Modify: `backend/app/services/chat/turn.py`
- Modify: `backend/app/services/chat/stream.py`
- Modify: `backend/app/services/conversation.py`, `backend/app/services/similarity.py` (any `user` relation access)

**Interfaces:**
- Produces: `Conversation.user_id: UUIDField(null=True)`, `Message.user_id: UUIDField(null=True)` (no FK). `save_turn(... user: Principal | None)` sets `user_id=user.id if user else None`.

- [ ] **Step 1: Write/adjust the failing test** — a turn saved with a `Principal` persists `user_id`:

```python
@pytest.mark.asyncio
async def test_save_turn_sets_user_id(db, make_principal):
    from app.services.chat.turn import save_turn
    p = make_principal(sub="11111111-1111-1111-1111-111111111111")
    saved = await save_turn(query="q", conversation_id=str(uuid.uuid4()), answer="a",
                            references=[], category=None, agency_ids=[], response_time=1,
                            user=p, succeeded=True)
    from app.repositories import conversation as repo
    conv = await repo.by_id(saved.conversation_id)
    assert str(conv.user_id) == p.id
```

Add a `make_principal` fixture to `tests/auth/conftest.py` or `tests/conftest.py`:

```python
@pytest.fixture
def make_principal():
    from app.auth.keycloak import Principal
    def _make(sub="00000000-0000-0000-0000-000000000001", role="user", scopes=()):
        return Principal(id=sub, email="u@e.co", display_name="U", role=role,
                         scopes=frozenset(scopes))
    return _make
```

- [ ] **Step 2: Run it to confirm failure** (`user` FK vs `user_id`).

- [ ] **Step 3: Change the model fields** in `app/models/conversation.py`:

```python
    # replace the `user = fields.ForeignKeyField("models.User", ...)` blocks with:
    user_id = fields.UUIDField(null=True)
```

Update `turn.py`/`stream.py` to pass and set `user_id=user.id if user else None` (the `Principal.id` is the sub). Replace any `.user` relation reads in `conversation.py`/`similarity.py` with `user_id` comparisons.

- [ ] **Step 4: Run the affected suites**

Run: `cd backend && uv run pytest -q -k "turn or conversation or similarity"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A backend/app/models/conversation.py backend/app/services backend/tests
git commit -m "refactor(model): store Keycloak sub as user_id on conversation/message"
```

### Task 9: Drop User/Session/UserAPIKey models and repository; aerich migration

**Files:**
- Delete: `backend/app/models/user.py`, `backend/app/models/session.py`
- Modify: `backend/app/models/__init__.py`
- Delete: `backend/app/repositories/user.py`; Modify `backend/app/repositories/__init__.py`
- Create: `backend/migrations/models/<n>_drop_local_auth.py` (aerich)

**Interfaces:**
- Produces: no `User`/`Session`/`UserAPIKey` ORM models; DB has no `users`, `sessions`, `user_api_keys` tables; `conversations.user_id` / `messages.user_id` are plain UUID columns.

- [ ] **Step 1: Delete the model files and drop them from the star-import** in `app/models/__init__.py`. Remove `UserAPIKey`/`User`/`Session` from `__all__` and imports. Delete `app/repositories/user.py` and its export.

- [ ] **Step 2: Generate the migration**

Run: `cd backend && uv run aerich migrate --name drop_local_auth`
Expected: a new migration file under `migrations/models/`.

- [ ] **Step 3: Inspect the migration** — confirm it drops `users`, `sessions`, `user_api_keys` and alters `conversations`/`messages` (`user_id` column, no FK). Hand-edit if aerich generated a `RENAME` instead of a drop.

- [ ] **Step 4: Run the full suite** (in-memory SQLite builds schema from models, so this validates the model layer)

Run: `cd backend && uv run pytest -q -k "not (cookie or api_key or session or ws)"`
Expected: PASS except the auth-transport tests slated for Phase 7.

- [ ] **Step 5: Commit**

```bash
git add -A backend/app/models backend/app/repositories backend/migrations
git rm backend/app/models/user.py backend/app/models/session.py backend/app/repositories/user.py
git commit -m "feat(db): drop users/sessions/user_api_keys; migrate user_id columns"
```

---

## Phase 6 — Apply per-route scopes (old gate still active as belt-and-suspenders)

Each task adds `Security(require_scope, scopes=[...])` per the authorization matrix.
Pattern for every route:

```python
from fastapi import Security
from app.auth.dependencies import require_scope
from app.auth.keycloak import Principal

@router.get("/statistics")
async def statistics(p: Principal = Security(require_scope, scopes=["dashboard:read"])):
    ...
```

Replace existing `Depends(require_admin)` and `Depends(get_current_user)` role guards
with the matrix scope. Import `User` type hints are replaced by `Principal`.

### Task 10: Agencies routers scopes

**Files:** `backend/app/routers/agencies/{__init__,crud,golden,lifecycle,logo,spec}.py`; tests under `tests/` touching agencies.

- [ ] **Step 1:** Write/adjust a test asserting: a `user`-scope token (`agency:list`) can `GET /api/v1/agencies` (200) but cannot `POST /api/v1/agencies` (403); an `agency:write` token can create (201). Use `make_token`.
- [ ] **Step 2:** Run it — confirm the create-forbidden case fails (currently allowed by `require_admin` only).
- [ ] **Step 3:** Apply scopes from the matrix: `GET /agencies` → `agency:list`; `GET /agencies/{id}` & health-history & golden GETs → `agency:read`; all writes, status, conformance, logo upload, mcp/discover, parse-specification, golden writes → `agency:write`.
- [ ] **Step 4:** Run `uv run pytest -q -k "agenc"`. Expected: PASS.
- [ ] **Step 5:** Commit `refactor(agency): enforce Keycloak scopes on agency routes`.

### Task 11: History + messages scopes and ownership

**Files:** `backend/app/routers/conversations.py`, `backend/app/routers/messages.py`, `backend/app/services/conversation.py`, `backend/app/services/similarity.py`, `backend/app/services/usage_context.py`, `tests/conftest.py`.

**Interfaces:** ownership uses scope, not role: a Principal with `conversation:read:all` sees every conversation; otherwise results are filtered to `principal.id`.

- [ ] **Step 1:** Write tests: `conversation:read:own` token sees only its own `user_id` rows; `conversation:read:all` token sees all; `message:rate` token can `PATCH /messages/{id}/rating`.
- [ ] **Step 2:** Run — confirm failure.
- [ ] **Step 3:** Apply scopes (matrix): history GETs → `conversation:read:own`; history POST/DELETE → `conversation:write:own`; message rating → `message:rate`. In the history service, branch on `"conversation:read:all" in principal.scopes` to decide all-vs-own; delete the old `role == "admin"` checks. Remove `current_api_key_id` from `app/services/usage_context.py` and from the `_reset_usage_context` fixture in `tests/conftest.py`.
- [ ] **Step 4:** Run `uv run pytest -q -k "history or conversation or message or usage"`. Expected: PASS.
- [ ] **Step 5:** Commit `refactor(history): scope-based ownership for conversations and message rating`.

### Task 12: Staff dashboards scopes

**Files:** `backend/app/routers/dashboard.py`, `executive_summary.py`, `insight.py`, `feedback.py`; related tests.

- [ ] **Step 1:** Write tests: a `staff` token (bundle scopes) reaches `/dashboard/statistics`, `/executive-summary`, `/agency-health`, `/usage-heatmap`, `/insight/usage`, `/feedback/statistics` (200) but not `/analytics-insights`, `/executive-summary/regenerate`, `/feedback/agencies/{id}/low-rated` (403).
- [ ] **Step 2:** Run — confirm failure.
- [ ] **Step 3:** Apply scopes (matrix): `dashboard:read`, `executive:read`, `executive:write` (regenerate), `health:read`, `usage:read` (heatmap + insight/usage), `analytics:read` (analytics-insights), `feedback:read` (statistics), `feedback:read:detail` (low-rated).
- [ ] **Step 4:** Run `uv run pytest -q -k "dashboard or executive or insight or feedback"`. Expected: PASS.
- [ ] **Step 5:** Commit `refactor(analytics): enforce Keycloak scopes on dashboards`.

### Task 13: Admin-only routers scopes

**Files:** `backend/app/routers/audit_log.py`, `connection_logs.py`, `llm.py`, `settings.py`, `popular_questions.py`; related tests.

- [ ] **Step 1:** Write tests: a token missing the scope gets 403; the matching admin scope gets 200 for one route in each file.
- [ ] **Step 2:** Run — confirm failure.
- [ ] **Step 3:** Apply scopes (matrix): `audit:read`; `connlog:read` (all connection-logs GETs); `llm:read`/`llm:write`; `settings:read`/`settings:write` (PUT + cache flush); `popular:read` (admin list) / `popular:write` (create/patch/delete/regenerate). The public popular-questions GET stays public (moves in Task 15 note — it is already `/public/popular-questions`).
- [ ] **Step 4:** Run `uv run pytest -q -k "audit or connection or language_model or settings or popular"`. Expected: PASS.
- [ ] **Step 5:** Commit `refactor(admin): enforce Keycloak scopes on admin routes`.

### Task 14: User management proxy to Keycloak Admin API

**Files:** Create `backend/app/services/keycloak_admin.py`; Modify `backend/app/routers/users.py`, `backend/app/services/user.py`; tests `backend/tests/test_users_proxy.py`.

**Interfaces:**
- Produces: `keycloak_admin.list_users(...)`, `get_user(id)`, `create_user(...)`, `update_user(id, ...)`, `set_enabled(id, bool)` — async, calling the Keycloak Admin REST API with a client-credentials token (cached). Routers require `user:manage`.

- [ ] **Step 1:** Write tests with the Keycloak Admin API mocked (monkeypatch `keycloak_admin._admin_get/_admin_post/...` or an httpx `MockTransport`): `GET /api/v1/users` with `user:manage` returns the mapped list; deactivate calls `set_enabled(id, False)`; a token without `user:manage` gets 403.
- [ ] **Step 2:** Run — confirm failure.
- [ ] **Step 3:** Implement `keycloak_admin.py` (client-credentials token via `settings.keycloak_token_url`, cached in a `TTLCache`; CRUD against `{KEYCLOAK_URL}/admin/realms/{realm}/users`), map Keycloak user representation to `schemas/user.py`, and rewrite `routers/users.py` handlers to call it with `Security(require_scope, scopes=["user:manage"])`. Delete the old DB-backed `services/user.py` internals (keep only mapping helpers if reused).
- [ ] **Step 4:** Run `uv run pytest -q tests/test_users_proxy.py`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(users): proxy user management to the Keycloak Admin API`.

---

## Phase 7 — Remove the role allowlist; MCP; delete dead auth

> **Design decision (user-approved):** there is NO runtime global gate. Authorization
> is per-route `require_scope` (deny-by-default: no valid token ⇒ 401 via
> `get_current_user`, missing scope ⇒ 403). Public routes carry no auth dependency.
> The "no route silently unprotected" guarantee is the CI **route-audit test** (Task 18),
> not a request-path chokepoint. This preserves the fail-closed *property* while keeping
> the suite green (the override-based tests never send a token, so a runtime token gate
> would 401 them — hence no runtime gate).

### Task 15: Delete the role allowlist (no runtime gate)

**Files:** `backend/app/auth/dependencies.py`, `backend/app/main.py`, `backend/app/middleware/session_refresh.py`; tests.

**Interfaces:**
- Produces: `enforce_role_allowlist`, every `_is_*` predicate, `_STAFF_GET_EXACT`, and `require_admin` are **deleted**. No `enforce_access` replacement — there is no global auth dependency. `SessionRefreshMiddleware` deleted.

- [ ] **Step 1:** Write `tests/auth/test_no_gate_access.py`: with `as_principal(scopes=["dashboard:read"], role="staff")`, `GET /api/v1/dashboard/statistics` ⇒ 200; a public route (`GET /api/v1/public/status`) ⇒ 200 with no override and no token; a scoped route with NO token and NO override ⇒ 401 (from `require_scope`'s `get_current_user`).
- [ ] **Step 2:** Run — confirm the no-token-401 case behaves (it may already pass via require_scope; the point is to lock it before deleting the allowlist).
- [ ] **Step 3:** In `app/auth/dependencies.py`, delete `enforce_role_allowlist`, all `_is_*` predicates, `_STAFF_GET_EXACT`, and `require_admin` (no longer referenced after Phase 6). In `app/main.py`, **remove the global `dependencies=[Depends(enforce_role_allowlist)]` argument entirely** (do not add a replacement), delete `app.add_middleware(SessionRefreshMiddleware)` and its import, and delete `app/middleware/session_refresh.py`.
- [ ] **Step 4:** Run the full suite (auth-transport legacy tests are removed in Task 17):

Run: `cd backend && OTEL_SDK_DISABLED=true uv run pytest -q -k "not (cookie or api_key_rest or ws_auth or session_refresh or auth_session)"`
Expected: PASS (baseline 6 OTEL failures aside).

- [ ] **Step 5:** Commit `feat(auth): remove role allowlist; enforcement is per-route scopes`.

### Task 16: Keep agent-proxy anonymous (no gate to bypass)

**Files:** `backend/app/routers/agent_proxy.py` (likely unchanged); `backend/tests`.

**Interfaces:**
- Produces: agent-proxy stays a normal router at `/api/v1/agent-proxy/{agency_id}` with **no `require_scope`**, so it is anonymously reachable (its own auth = UUID check + agency credentials, unchanged). It is added to the route-audit whitelist in Task 18. No re-mount — the spec's re-mount rationale was to bypass the runtime gate, which no longer exists.

- [ ] **Step 1:** Write/confirm a test: `POST /api/v1/agent-proxy/{uuid}` with no token reaches the proxy service (mock the upstream) — i.e. not 401.
- [ ] **Step 2:** Run it. If it already passes (no gate, no scope on the route), the task is a no-op beyond the test + the Task 18 whitelist entry — record that and proceed.
- [ ] **Step 3:** Ensure `agent_proxy.py` has no `require_scope`/`get_current_user` dependency (it should not). Do NOT re-mount.
- [ ] **Step 4:** Run `uv run pytest -q -k "agent_proxy"`. Expected: PASS.
- [ ] **Step 5:** Commit `test(agent-proxy): confirm anonymous reachability under scope model` (skip if no changes were needed beyond Task 18).

### Task 17: MCP bearer auth; delete dead auth surfaces; trim auth router

**Files:** `backend/app/mcp/server.py`; delete `backend/app/routers/api_key.py`, `backend/app/services/api_key.py`, `backend/app/services/auth_session.py`, `backend/app/auth/security.py`, `backend/app/auth/ws.py`; Modify `backend/app/routers/auth.py`, `backend/app/services/seed.py`, `backend/app/main.py`; delete obsolete auth tests.

**Interfaces:**
- Produces: MCP `AuthMiddleware` verifies a Keycloak bearer when present (via `verify_token`), else anonymous; `GET /authentication/me` is the only remaining auth route; `run_seed_admin` gone.

- [ ] **Step 1:** Write/adjust tests: MCP `list_agency` works anonymously and strips auth headers for non-admin (existing `test_mcp_role_access.py` intent), and now recognizes an admin bearer; `GET /api/v1/authentication/me` returns the Principal for a valid token and 401 without one. Delete `test_session_cookie_auth.py`, `test_api_key_rest_auth.py`, and WS-auth tests.
- [ ] **Step 2:** Run — confirm the `/me` test fails and imports of deleted modules are gone.
- [ ] **Step 3:** 
  - In `mcp/server.py` `AuthMiddleware`, replace the `UserAPIKey` hash lookup with: if an `Authorization: Bearer` header is present, `verify_token(token)` → set `user_id`/`user_is_admin` from the Principal; on `InvalidToken`, treat as anonymous. Remove `hash_api_key`, `UserAPIKey`, `User` imports.
  - In `routers/auth.py`, delete login/logout/anonymous/change-password and `PATCH /me`; keep only `GET /me` returning `{ id, email, display_name, role }` from `Depends(get_current_user)`.
  - Delete `routers/api_key.py`, `services/api_key.py`, `services/auth_session.py`, `auth/security.py`, `auth/ws.py`. Remove `app.include_router(api_key.router, ...)` and the `api_key` import from `main.py`.
  - In `services/seed.py`, delete `run_seed_admin`; remove its call from the `main.py` lifespan.
- [ ] **Step 4:** Run the full suite

Run: `cd backend && uv run pytest -q`
Expected: PASS (green, no legacy auth tests remain).

- [ ] **Step 5:** Commit

```bash
git add -A backend/app backend/tests
git rm backend/app/routers/api_key.py backend/app/services/api_key.py \
       backend/app/services/auth_session.py backend/app/auth/security.py backend/app/auth/ws.py
git commit -m "feat(auth): MCP bearer auth; remove password/session/API-key surfaces"
```

---

## Phase 8 — Safety net and closeout

### Task 18: Route-audit test (no unclassified route)

**Files:** Create `backend/tests/test_route_audit.py`.

**Interfaces:** asserts every `/api/v1/*` route is either under `/api/v1/public/` or carries a `require_scope` dependency. This test is the sole "no route silently unprotected" guarantee (there is no runtime gate), so it must be exhaustive. Explicit auth-exempt whitelist: `GET /authentication/me` (valid token, no scope) and every `POST/GET/PUT/PATCH/DELETE /api/v1/agent-proxy/{agency_id}` method (external OneChat callback, its own auth). Any other un-scoped, non-public route is a FAIL.

- [ ] **Step 1: Write the test**

```python
from app.main import app
from app.auth.dependencies import require_scope

_WHITELIST_EXACT = {("GET", "/api/v1/authentication/me")}
_WHITELIST_PREFIX = ("/api/v1/agent-proxy/",)  # external OneChat callback, own auth

def _uses_require_scope(route) -> bool:
    for dep in getattr(route.dependant, "dependencies", []):
        if getattr(dep, "call", None) is require_scope:
            return True
    return False

def test_every_api_route_is_classified():
    offenders = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if not path.startswith("/api/v1/"):
            continue
        if path.startswith("/api/v1/public/"):
            continue
        if any(path.startswith(p) for p in _WHITELIST_PREFIX):
            continue
        for m in methods:
            if (m, path) in _WHITELIST_EXACT:
                continue
            if not _uses_require_scope(route):
                offenders.append(f"{m} {path}")
    assert not offenders, f"unclassified routes: {sorted(set(offenders))}"
```

- [ ] **Step 2: Run it**

Run: `cd backend && uv run pytest -q tests/test_route_audit.py`
Expected: PASS. If it lists offenders, add the correct scope from the matrix to each.

- [ ] **Step 3: Commit** `test(auth): route-audit gate against unclassified endpoints`.

### Task 19: Full suite, import smoke, docs

**Files:** `backend/CONTEXT.md`, `CONTEXT.md`.

- [ ] **Step 1: Full suite**

Run: `cd backend && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 2: Import smoke under the app runner**

Run: `cd backend && uv run python -c "import app.main; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Update CONTEXT.md** with the Keycloak migration summary (auth model, dropped tables, scope matrix location, moved URLs).

- [ ] **Step 4: Commit** `docs(context): record Keycloak auth migration`.

---

## Self-review notes

- **Spec coverage:** §4 → Task 4; §5.1/§5.1a → Tasks 6,7,15,16; §5.2/§5.3 → Phase 6 + Task 2; §5.4 → Task 11; §5.5 → Task 18; §6 → Tasks 8,9; §7 → Tasks 6,7,10–17; §8 → Task 14; §9 → Tasks 1,2; §11 → Tasks 3,4 + each phase's tests. All covered.
- **Non-regression:** old allowlist stays through Phase 6; the swap (Task 15) lands only after every route carries a scope, so access never widens between tasks.
- **Type consistency:** `Principal` (Task 4) is the single principal type used by `get_current_user`, `require_scope`, `save_turn`, and services throughout.
