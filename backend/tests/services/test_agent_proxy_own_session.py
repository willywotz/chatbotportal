"""agent_proxy is a logging/telemetry write path: agency lookup, the call
counter, and the ConnectionLog write each open their own short-lived session
(app.core.db.AsyncSessionLocal) so they persist independently of any request
rollback. Bind that session factory to the test's own connection (same
pattern as test_rate_limit.py) so writes are visible/rolled back with it.
"""
import json
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ApiError
from app.features.agency.models.agency import Agency
from app.core.models.connection_log import ConnectionLog
from app.features.agency.repositories import agency as agency_repo
from app.features.mcp.services import agent_proxy

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

    log = (await db_session.execute(
        select(ConnectionLog).where(ConnectionLog.agency_id == agency.id)
    )).scalars().first()
    assert log.action == "proxy"
    assert log.connection_type == "API"
    assert log.status == "success"
    assert "Query: hi" in log.detail


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

    log = (await db_session.execute(
        select(ConnectionLog).where(ConnectionLog.agency_id == agency.id)
    )).scalars().first()
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

    log = (await db_session.execute(
        select(ConnectionLog).where(ConnectionLog.agency_id == agency.id)
    )).scalars().first()
    assert log.status == "error"
