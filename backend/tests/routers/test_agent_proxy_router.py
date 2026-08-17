import json
import uuid

import httpx
import pytest

from app.main import app
from app.models import Agency
from app.services import agent_proxy


@pytest.fixture
def fake_upstream(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"agency-answer")

    real = agent_proxy.proxy

    async def patched(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return await real(**kwargs)

    monkeypatch.setattr(agent_proxy, "proxy", patched)


async def _agency() -> Agency:
    return await Agency.create(
        name="Dept", connection_type="API", status="active",
        endpoint_url="http://upstream.test/chat",
        expected_payload={"query": "{q}"}, api_headers=[],
    )


async def test_proxy_route_streams_without_portal_auth(db, fake_upstream):
    agency = await _agency()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/agent-proxy/{agency.id}",
            content=json.dumps({"query": "hi"}),
        )
    assert resp.status_code == 200
    assert resp.content == b"agency-answer"


async def test_proxy_route_bad_uuid_returns_400(db, fake_upstream):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agent-proxy/not-a-uuid", content=b"{}")
    assert resp.status_code == 400
