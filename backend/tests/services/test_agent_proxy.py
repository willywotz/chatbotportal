"""agent_proxy opens its own short-lived session (app.db.AsyncSessionLocal) for
the agency lookup, the call counter, and the ConnectionLog write, so bind that
factory to the test's own connection (same pattern as test_agent_proxy_own_session.py)
so writes are visible/rolled back with it.
"""
import json
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import ApiError
from app.models.agency import Agency
from app.models.connection_log import ConnectionLog
from app.repositories import agency as agency_repo
from app.services import agent_proxy

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(agent_proxy, "AsyncSessionLocal", factory)


async def _agency(db_session, **over) -> Agency:
    data = dict(
        name="Dept", connection_type="API", status="active",
        endpoint_url="http://upstream.test/chat",
        expected_payload={"query": "{q}", "session_id": "__conversation_id__"},
        api_headers=[{"name": "Authorization", "value": "Bearer up-secret"}],
    )
    data.update(over)
    agency = await agency_repo.create(db_session, **data)
    await db_session.flush()
    return agency


def _upstream(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def _drain(stream) -> bytes:
    out = bytearray()
    async for chunk in stream:
        out.extend(chunk)
    return bytes(out)


async def _log_for(db_session, agency: Agency) -> ConnectionLog:
    return (await db_session.execute(
        select(ConnectionLog).where(ConnectionLog.agency_id == agency.id)
    )).scalars().first()


async def test_bad_uuid_raises_400(db_session):
    with pytest.raises(ApiError) as e:
        await agent_proxy.proxy(agency_id="not-a-uuid", method="POST", headers={}, body=b"{}")
    assert e.value.status == 400


async def test_unknown_agency_raises_404(db_session):
    with pytest.raises(ApiError) as e:
        await agent_proxy.proxy(
            agency_id=str(uuid.uuid4()), method="POST", headers={}, body=b"{}",
        )
    assert e.value.status == 404


async def test_success_streams_body_and_status(db_session):
    agency = await _agency(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hello-answer")

    status_code, _headers, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    body = await _drain(stream)
    assert status_code == 200
    assert body == b"hello-answer"


async def test_success_increments_calls_and_logs(db_session):
    agency = await _agency(db_session, total_calls=0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    _sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    await _drain(stream)

    # agent_proxy updated the row through a different (short-lived) session;
    # db_session's identity map still holds the pre-update instance.
    await db_session.refresh(agency)
    assert agency.total_calls == 1

    log = await _log_for(db_session, agency)
    assert log.action == "proxy"
    assert log.connection_type == "API"
    assert log.status == "success"
    assert "Query: hi" in log.detail


async def test_strips_x_forwarded_and_sets_api_headers(db_session):
    agency = await _agency(db_session)
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


async def test_upstream_5xx_logs_error_and_no_increment(db_session):
    agency = await _agency(db_session, total_calls=0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"down")

    sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    await _drain(stream)

    await db_session.refresh(agency)
    assert sc == 503
    assert agency.total_calls == 0

    log = await _log_for(db_session, agency)
    assert log.status == "error"


async def test_connection_error_raises_502_and_logs(db_session):
    agency = await _agency(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ApiError) as e:
        await agent_proxy.proxy(
            agency_id=str(agency.id), method="POST", headers={},
            body=b"{}", transport=_upstream(handler),
        )
    assert e.value.status == 502

    log = await _log_for(db_session, agency)
    assert log.status == "error"


async def test_response_body_truncated_in_log(db_session, monkeypatch):
    monkeypatch.setattr(agent_proxy.settings, "CONNECTION_LOG_BODY_MAX_CHARS", 10)
    agency = await _agency(db_session)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 100)

    _sc, _h, stream = await agent_proxy.proxy(
        agency_id=str(agency.id), method="POST", headers={},
        body=json.dumps({"query": "hi"}).encode(), transport=_upstream(handler),
    )
    assert await _drain(stream) == b"x" * 100  # caller still gets the full body
    log = await _log_for(db_session, agency)
    assert len(log.response_body) == 10
