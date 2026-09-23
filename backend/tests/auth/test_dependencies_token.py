import pytest
from fastapi import Depends, FastAPI, Security
from httpx import ASGITransport, AsyncClient

from app.core.security.dependencies import get_current_user, require_scope
from app.core.security.principal import Principal


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
