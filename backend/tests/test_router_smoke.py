"""Proves the `client` test harness: routers serve real HTTP requests against
the Postgres testcontainer via `get_db`."""
import pytest

from app.models.agency import Agency

pytestmark = pytest.mark.asyncio


async def test_health_returns_200(client):
    res = await client.get("/health")
    assert res.status_code == 200


async def test_agencies_list_returns_200_for_seeded_agency(client, db_session, as_principal):
    db_session.add(Agency(name="Smoke Test Agency"))
    await db_session.flush()
    as_principal(scopes=["agency:list"])

    res = await client.get("/api/v1/agencies")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert any(a["name"] == "Smoke Test Agency" for a in body["data"])
