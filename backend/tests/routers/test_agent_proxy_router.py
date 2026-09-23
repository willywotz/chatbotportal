import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agency import Agency
from app.repositories import agency as agency_repo
from app.services import agent_proxy

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    """agent_proxy opens its own short-lived session; bind it to the test's
    connection so it sees the agency the client's db_session created."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(agent_proxy, "AsyncSessionLocal", factory)


@pytest.fixture
def fake_upstream(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"agency-answer",
            headers={"content-encoding": "identity", "x-agency": "keep"},
        )

    real = agent_proxy.proxy

    async def patched(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return await real(**kwargs)

    monkeypatch.setattr(agent_proxy, "proxy", patched)


async def _agency(db_session) -> Agency:
    agency = await agency_repo.create(
        db_session,
        name="Dept", connection_type="API", status="active",
        endpoint_url="http://upstream.test/chat",
        expected_payload={"query": "{q}"}, api_headers=[],
    )
    await db_session.flush()
    return agency


async def test_proxy_route_streams_without_portal_auth(client, db_session, fake_upstream):
    agency = await _agency(db_session)
    resp = await client.post(
        f"/api/v1/agent-proxy/{agency.id}",
        content=json.dumps({"query": "hi"}),
    )
    assert resp.status_code == 200
    assert resp.content == b"agency-answer"
    # Hop-by-hop headers must not leak to the client; other headers pass through.
    assert "content-encoding" not in resp.headers
    assert resp.headers.get("x-agency") == "keep"


async def test_proxy_route_bad_uuid_returns_400(client, db_session, fake_upstream):
    resp = await client.post("/api/v1/agent-proxy/not-a-uuid", content=b"{}")
    assert resp.status_code == 400
