"""The ?traceparent query fallback must continue the trace on the agent-proxy
route. OneChat drops the header but keeps the query string; the main app wrapped
with QueryTraceparentASGI promotes it to a header before OTel extraction.
"""
import json

import httpx

from app.main import asgi_app
from app.models import Agency
from app.services import agent_proxy

_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
_QUERY_TRACEPARENT = f"00-{_TRACE_ID}-b7ad6b7169203331-01"


async def test_query_traceparent_promoted_to_upstream_header(db, monkeypatch):
    agency = await Agency.create(
        name="Dept", connection_type="API", status="active",
        endpoint_url="http://upstream.test/chat", expected_payload={}, api_headers=[],
    )

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, content=b"ok")

    real = agent_proxy.proxy

    async def patched(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return await real(**kwargs)

    monkeypatch.setattr(agent_proxy, "proxy", patched)

    transport = httpx.ASGITransport(app=asgi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/agent-proxy/{agency.id}?traceparent={_QUERY_TRACEPARENT}",
            content=json.dumps({"query": "hi"}),  # no traceparent header
        )

    assert resp.status_code == 200
    assert _TRACE_ID in seen.get("traceparent", "")
