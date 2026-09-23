"""HTTP surface of the self-hosted OIDC provider.

Public endpoints (no bearer, except userinfo): discovery and JWKS at the
issuer root under `/.well-known`, and the authorization endpoint (with its
server-rendered login page), token endpoint (authorization_code +
refresh_token) and userinfo under `/oauth2`."""
from __future__ import annotations

import html
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.identity.oidc import keys, provider
from app.features.identity.oidc.passwords import verify_password
from app.core.security.tokens import verify_token
from app.core.security.principal import InvalidToken
from app.core.config import settings
from app.core.db import get_db
from app.features.identity.repositories import user as user_repo

router = APIRouter(tags=["OIDC"])


def _oauth_error(error: str, description: str = "", status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": description}, status_code=status_code)


def _valid_client(client_id: str) -> bool:
    return client_id == settings.OIDC_CLIENT_ID


def _valid_redirect(redirect_uri: str) -> bool:
    return redirect_uri in settings.OIDC_ALLOWED_REDIRECT_URIS


@router.get("/.well-known/openid-configuration", summary="OIDC discovery document")
async def discovery() -> dict:
    issuer = settings.OIDC_ISSUER
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth2/authorize",
        "token_endpoint": f"{issuer}/oauth2/token",
        "jwks_uri": f"{issuer}/.well-known/jwks.json",
        "userinfo_endpoint": f"{issuer}/oauth2/userinfo",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
        "claims_supported": ["sub", "email", "name", "role", "scope"],
    }


@router.get("/.well-known/jwks.json", summary="JSON Web Key Set")
async def jwks() -> dict:
    return keys.public_jwks()


def _login_page(params: dict, error: str = "") -> HTMLResponse:
    hidden = "".join(
        f'<input type="hidden" name="{html.escape(str(name), quote=True)}" '
        f'value="{html.escape(str(value), quote=True)}">'
        for name, value in params.items()
        if value is not None
    )
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    page = f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>เข้าสู่ระบบ · Agentic AI Chatbot</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --background: 210 33% 98%;
    --foreground: 215 25% 15%;
    --card: 0 0% 100%;
    --card-foreground: 215 25% 15%;
    --primary: 213 70% 45%;
    --primary-foreground: 0 0% 100%;
    --muted-foreground: 215 15% 50%;
    --border: 214 25% 90%;
    --input: 214 25% 88%;
    --ring: 213 70% 45%;
    --destructive: 0 72% 55%;
    --radius: 0.625rem;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --background: 220 20% 10%;
      --foreground: 210 30% 92%;
      --card: 220 18% 14%;
      --card-foreground: 210 30% 92%;
      --primary: 213 65% 55%;
      --primary-foreground: 0 0% 100%;
      --muted-foreground: 215 15% 55%;
      --border: 220 15% 22%;
      --input: 220 15% 22%;
      --ring: 213 65% 55%;
      --destructive: 0 62% 45%;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Sarabun', sans-serif; font-weight: 300; line-height: 1.6;
         background: hsl(var(--background)); color: hsl(var(--foreground));
         display: flex; min-height: 100vh; align-items: center; justify-content: center;
         margin: 0; padding: 1rem; }}
  .card {{ background: hsl(var(--card)); color: hsl(var(--card-foreground));
          border: 1px solid hsl(var(--border)); border-radius: var(--radius);
          box-shadow: 0 1px 3px 0 hsl(215 25% 15% / .08), 0 1px 2px -1px hsl(215 25% 15% / .08);
          padding: 2rem; width: 100%; max-width: 28rem; }}
  .brand {{ text-align: center; font-size: 1.5rem; font-weight: 600; margin: 0;
           background: linear-gradient(135deg, hsl(213 70% 40%) 0%, hsl(200 50% 50%) 100%);
           -webkit-background-clip: text; -webkit-text-fill-color: transparent;
           background-clip: text; }}
  .subtitle {{ text-align: center; font-size: .875rem; color: hsl(var(--muted-foreground));
              margin: .5rem 0 1.75rem; }}
  label {{ display: block; font-size: .875rem; font-weight: 500; margin: 1rem 0 .375rem; }}
  input[type=email], input[type=password] {{ width: 100%; padding: .625rem .75rem;
         font: inherit; border-radius: calc(var(--radius) - 2px);
         border: 1px solid hsl(var(--input)); background: hsl(var(--card));
         color: hsl(var(--foreground)); }}
  input[type=email]:focus, input[type=password]:focus {{ outline: none;
         border-color: hsl(var(--ring)); box-shadow: 0 0 0 3px hsl(var(--ring) / .25); }}
  button {{ margin-top: 1.5rem; width: 100%; padding: .625rem; font: inherit; font-weight: 500;
           border: 0; border-radius: calc(var(--radius) - 2px);
           background: hsl(var(--primary)); color: hsl(var(--primary-foreground));
           cursor: pointer; transition: opacity .15s ease; }}
  button:hover {{ opacity: .9; }}
  .error {{ color: hsl(var(--destructive)); font-size: .875rem; margin: .75rem 0 0; }}
</style>
</head>
<body>
<form class="card" method="post" action="{settings.OIDC_ISSUER}/oauth2/authorize">
  <h1 class="brand">Agentic AI Chatbot</h1>
  <p class="subtitle">ระบบบูรณาการข้อมูลหน่วยงานภาครัฐ</p>
  {hidden}
  <label for="email">อีเมล (Email)</label>
  <input id="email" name="email" type="email" autocomplete="username" required autofocus>
  <label for="password">รหัสผ่าน (Password)</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
  {error_html}
  <button type="submit">เข้าสู่ระบบ</button>
</form>
</body>
</html>"""
    return HTMLResponse(page)


def _authorize_params(
    client_id: str, redirect_uri: str, response_type: str, code_challenge: str,
    code_challenge_method: str, state: str | None, scope: str | None, nonce: str | None,
) -> dict:
    return {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": response_type,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "state": state,
        "scope": scope,
        "nonce": nonce,
    }


@router.get("/oauth2/authorize", summary="Authorization endpoint — render login")
async def authorize_get(
    client_id: str,
    redirect_uri: str,
    response_type: str = "code",
    code_challenge: str = "",
    code_challenge_method: str = "S256",
    state: str | None = None,
    scope: str | None = None,
    nonce: str | None = None,
):
    if not _valid_client(client_id):
        return _oauth_error("unauthorized_client", "unknown client_id")
    if not _valid_redirect(redirect_uri):
        return _oauth_error("invalid_request", "redirect_uri not allowed")
    if response_type != "code":
        return _oauth_error("unsupported_response_type", "only response_type=code is supported")
    if code_challenge_method != "S256" or not code_challenge:
        return _oauth_error("invalid_request", "S256 code_challenge is required")
    params = _authorize_params(
        client_id, redirect_uri, response_type, code_challenge,
        code_challenge_method, state, scope, nonce,
    )
    return _login_page(params)


@router.post("/oauth2/authorize", summary="Authorization endpoint — verify credentials")
async def authorize_post(
    email: str = Form(...),
    password: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    response_type: str = Form("code"),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form("S256"),
    state: str | None = Form(None),
    scope: str | None = Form(None),
    nonce: str | None = Form(None),
    session: AsyncSession = Depends(get_db),
):
    if not _valid_client(client_id):
        return _oauth_error("unauthorized_client", "unknown client_id")
    if not _valid_redirect(redirect_uri):
        return _oauth_error("invalid_request", "redirect_uri not allowed")

    params = _authorize_params(
        client_id, redirect_uri, response_type, code_challenge,
        code_challenge_method, state, scope, nonce,
    )
    user = await user_repo.get_by_email(session, email)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return _login_page(params, error="อีเมลหรือรหัสผ่านไม่ถูกต้อง (invalid email or password)")

    code = await provider.issue_authorization_code(
        session, user=user, client_id=client_id, redirect_uri=redirect_uri,
        code_challenge=code_challenge, scope=scope or "openid",
    )
    query = {"code": code}
    if state is not None:
        query["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urlencode(query)}", status_code=302)


@router.post("/oauth2/token", summary="Token endpoint")
async def token(
    grant_type: str = Form(...),
    code: str | None = Form(None),
    code_verifier: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    refresh_token: str | None = Form(None),
    client_id: str = Form(...),
    session: AsyncSession = Depends(get_db),
):
    try:
        if grant_type == "authorization_code":
            if not (code and code_verifier and redirect_uri):
                return _oauth_error("invalid_request", "missing code, code_verifier or redirect_uri")
            result = await provider.exchange_code(
                session, code=code, code_verifier=code_verifier,
                redirect_uri=redirect_uri, client_id=client_id,
            )
        elif grant_type == "refresh_token":
            if not refresh_token:
                return _oauth_error("invalid_request", "missing refresh_token")
            result = await provider.refresh(session, refresh_token=refresh_token, client_id=client_id)
        else:
            return _oauth_error("unsupported_grant_type", grant_type)
    except provider.OAuthError as exc:
        return _oauth_error(exc.error, exc.description)
    return JSONResponse(result)


@router.get("/oauth2/userinfo", summary="UserInfo endpoint")
async def userinfo(request: Request) -> JSONResponse:
    auth = request.headers.get("authorization", "")
    token_value = auth[7:] if auth.lower().startswith("bearer ") else ""
    try:
        principal = verify_token(token_value)
    except InvalidToken:
        return _oauth_error("invalid_token", "invalid or expired token", status_code=401)
    return JSONResponse({"sub": principal.id, "email": principal.email, "name": principal.display_name})
