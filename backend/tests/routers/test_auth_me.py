"""GET /api/v1/authentication/me — the only remaining auth route."""

from httpx import ASGITransport, AsyncClient

from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_me_with_valid_token_returns_principal_fields(make_token):
    token = make_token(role="admin", email="a@b.co")
    async with await _client() as c:
        r = await c.get("/api/v1/authentication/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "a@b.co"
    assert body["role"] == "admin"
    assert body["id"]
    assert "display_name" in body


async def test_me_without_token_is_401():
    async with await _client() as c:
        r = await c.get("/api/v1/authentication/me")
    assert r.status_code == 401
