import json
import uuid

import httpx
import pytest

from app.errors import ApiError
from app.models import Agency, ConnectionLog
from app.services import agent_proxy


async def _agency(**over):
    data = dict(
        name="Dept", connection_type="API", status="active",
        endpoint_url="http://upstream.test/chat",
        expected_payload={"query": "{q}", "session_id": "__conversation_id__"},
        api_headers=[{"name": "Authorization", "value": "Bearer up-secret"}],
    )
    data.update(over)
    return await Agency.create(**data)


def _upstream(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def _drain(stream) -> bytes:
    out = bytearray()
    async for chunk in stream:
        out.extend(chunk)
    return bytes(out)


async def test_bad_uuid_raises_400(db):
    with pytest.raises(ApiError) as e:
        await agent_proxy.proxy(agency_id="not-a-uuid", method="POST", headers={}, body=b"{}")
    assert e.value.status == 400


async def test_unknown_agency_raises_404(db):
    with pytest.raises(ApiError) as e:
        await agent_proxy.proxy(
            agency_id=str(uuid.uuid4()), method="POST", headers={}, body=b"{}",
        )
    assert e.value.status == 404


async def test_success_streams_body_and_status(db):
    agency = await _agency()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hello-answer")

    status_code, _headers, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    body = await _drain(stream)
    assert status_code == 200
    assert body == b"hello-answer"


async def test_success_increments_calls_and_logs(db):
    agency = await _agency(total_calls=0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    _sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    await _drain(stream)
    await agency.refresh_from_db()
    assert agency.total_calls == 1
    log = await ConnectionLog.filter(agency_id=agency.id).first()
    assert log.action == "proxy"
    assert log.connection_type == "API"
    assert log.status == "success"
    assert "Query: hi" in log.detail


async def test_strips_x_forwarded_and_sets_api_headers(db):
    agency = await _agency()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, content=b"ok")

    _sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST",
        headers={"X-Forwarded-For": "1.2.3.4", "X-Forwarded-Host": "x",
                 "Host": "portal.example", "Accept": "*/*"},
        body=b"{}", transport=_upstream(handler),
    )
    await _drain(stream)
    assert not any(k.lower().startswith("x-forwarded") for k in seen)
    assert seen.get("authorization") == "Bearer up-secret"
    # The upstream Host must come from the endpoint URL, not the portal's Host.
    assert seen.get("host") == "upstream.test"


async def test_upstream_5xx_logs_error_and_no_increment(db):
    agency = await _agency(total_calls=0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"down")

    sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    await _drain(stream)
    await agency.refresh_from_db()
    assert sc == 503
    assert agency.total_calls == 0
    log = await ConnectionLog.filter(agency_id=agency.id).first()
    assert log.status == "error"


async def test_connection_error_raises_502_and_logs(db):
    agency = await _agency()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ApiError) as e:
        await agent_proxy.proxy(
            agency_id=str(agency.id), method="POST", headers={},
            body=b"{}", transport=_upstream(handler),
        )
    assert e.value.status == 502
    log = await ConnectionLog.filter(agency_id=agency.id).first()
    assert log.status == "error"


async def test_response_body_truncated_in_log(db, monkeypatch):
    monkeypatch.setattr(agent_proxy.settings, "CONNECTION_LOG_BODY_MAX_CHARS", 10)
    agency = await _agency()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 100)

    _sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    assert await _drain(stream) == b"x" * 100  # caller still gets the full body
    log = await ConnectionLog.filter(agency_id=agency.id).first()
    assert len(log.response_body) == 10
