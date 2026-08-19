"""HTTP-level scope enforcement for GET/POST /api/v1/agencies.

A plain `user` role carrying only `agency:list` may browse the list (the
Architecture page) but must not create an agency; `agency:write` is required
for that.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.usefixtures("db")
async def test_list_agencies_allowed_with_agency_list_scope(as_principal):
    as_principal(role="user", scopes=["agency:list"])
    async with await _client() as c:
        r = await c.get("/api/v1/agencies")
    assert r.status_code == 200


@pytest.mark.usefixtures("db")
async def test_create_agency_forbidden_with_only_agency_list_scope(as_principal):
    as_principal(role="user", scopes=["agency:list"])
    async with await _client() as c:
        r = await c.post("/api/v1/agencies", json={"name": "New", "short_name": "N"})
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_create_agency_allowed_with_agency_write_scope(as_principal):
    as_principal(role="user", scopes=["agency:write"])
    async with await _client() as c:
        r = await c.post("/api/v1/agencies", json={"name": "New", "short_name": "N"})
    assert r.status_code == 201
