import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.errors import ApiError
from app.models.agency import Agency, AgencyStatus, ConnectionType
from app.models.connection_log import ConnectionLog

pytestmark = pytest.mark.asyncio


async def _agency(session, **fields):
    ag = Agency(name=fields.pop("name", "A"), short_name=fields.pop("short_name", "A"),
                connection_type=fields.pop("connection_type", ConnectionType.API), **fields)
    session.add(ag)
    await session.flush()
    return ag


async def test_parse_spec_raises_on_http_error():
    from app.services.agency import parse_spec
    from app.services.llm import LlmError

    with patch("app.services.llm.chat", AsyncMock(side_effect=LlmError("parse_spec: provider returned 429", status=429))):
        with pytest.raises(LlmError):
            await parse_spec("some spec text")


async def test_get_agency_or_404_raises_for_missing_agency(db_session):
    from app.services.agency import get_agency_or_404

    with pytest.raises(ApiError) as exc:
        await get_agency_or_404(db_session, uuid.uuid4())
    assert exc.value.status == 404
    assert exc.value.message == "Agency not found"


async def test_get_agency_or_404_returns_the_agency(db_session):
    from app.services.agency import get_agency_or_404

    created = await _agency(db_session)
    found = await get_agency_or_404(db_session, created.id)
    assert found.id == created.id


async def test_list_agencies_filters_by_status_connection_and_search(db_session):
    from app.services.agency import list_agencies

    await _agency(db_session, name="DOPA", short_name="d", connection_type=ConnectionType.API, status=AgencyStatus.active)
    await _agency(db_session, name="MOI", short_name="m", connection_type=ConnectionType.MCP, status=AgencyStatus.draft)

    all_agencies, total = await list_agencies(db_session, status_filter="all", connection_type=None, search=None)
    assert total == 2
    assert len(all_agencies) == 2

    active_only, active_total = await list_agencies(db_session, status_filter="active", connection_type=None, search=None)
    assert active_total == 1
    assert active_only[0].name == "DOPA"

    mcp_only, mcp_total = await list_agencies(db_session, status_filter="all", connection_type="mcp", search=None)
    assert mcp_total == 1
    assert mcp_only[0].name == "MOI"

    searched, searched_total = await list_agencies(db_session, status_filter="all", connection_type=None, search="dop")
    assert searched_total == 1
    assert searched[0].name == "DOPA"


async def test_create_agency_persists_endpoints_and_headers(db_session):
    from app.schemas.agency import AgencyCreate
    from app.services.agency import create_agency

    body = AgencyCreate(
        name="A", short_name="a", connection_type="API", status="draft",
        api_endpoints=[{"method": "GET", "path": "/x", "description": "d"}],
        api_headers=[{"name": "X", "value": "1", "description": ""}],
    )
    agency = await create_agency(db_session, body)
    assert agency.id is not None
    assert agency.api_endpoints == [{"method": "GET", "path": "/x", "description": "d"}]
    assert agency.api_headers == [{"name": "X", "value": "1", "description": ""}]


async def test_replace_agency_overwrites_fields(db_session):
    from app.schemas.agency import AgencyCreate
    from app.services.agency import replace_agency

    agency = await _agency(db_session, name="old", short_name="o", connection_type=ConnectionType.API)
    body = AgencyCreate(name="new", short_name="n", connection_type="MCP")
    updated = await replace_agency(db_session, agency, body)
    assert updated.name == "new"
    assert updated.connection_type == "MCP"


async def test_update_agency_demotes_active_agency_on_connection_identity_change(db_session):
    from app.schemas.agency import AgencyUpdate
    from app.services.agency import update_agency

    agency = await _agency(
        db_session, status=AgencyStatus.active,
        endpoint_url="https://old.example.com", conformance_report={"passed": True, "checks": []},
    )
    updated = await update_agency(db_session, agency, AgencyUpdate(endpoint_url="https://new.example.com"))
    assert updated.status == "draft"
    assert updated.conformance_report is None


async def test_delete_agency_removes_the_row(db_session):
    from app.repositories import agency as agency_repo
    from app.services.agency import delete_agency

    agency = await _agency(db_session)
    await delete_agency(db_session, agency)
    await db_session.flush()
    assert await agency_repo.by_id(db_session, agency.id) is None


async def test_increment_calls_persists_the_counter(db_session):
    from app.repositories import agency as agency_repo
    from app.services.agency import increment_calls

    agency = await _agency(db_session, total_calls=1)
    updated = await increment_calls(db_session, agency)
    assert updated.total_calls == 2
    refreshed = await agency_repo.by_id(db_session, agency.id)
    assert refreshed.total_calls == 2


async def test_run_connection_test_logs_a_connection_log_row(db_session):
    from sqlalchemy import select

    from app.services.agency import run_connection_test

    agency = await _agency(db_session, endpoint_url="https://x.example")
    fake_result = {"success": True, "protocol": "REST API", "version": "-", "steps": [], "latency": "12ms", "statusCode": 200}
    with patch("app.services.agency.test_connection", AsyncMock(return_value=fake_result)):
        raw = await run_connection_test(db_session, agency)
    assert raw["success"] is True
    logs = (await db_session.execute(select(ConnectionLog).where(ConnectionLog.agency_id == agency.id))).scalars().all()
    assert len(logs) == 1
    assert logs[0].latency_ms == 12


async def test_run_connection_test_recovers_auto_maintenance(db_session):
    from app.services.agency import run_connection_test

    agency = await _agency(
        db_session, endpoint_url="https://x.example",
        status=AgencyStatus.maintenance, auto_maintenance=True,
    )
    fake_result = {"success": True, "protocol": "REST API", "version": "-", "steps": [], "latency": "5ms", "statusCode": 200}
    with patch("app.services.agency.test_connection", AsyncMock(return_value=fake_result)):
        await run_connection_test(db_session, agency)
    assert agency.status == "active"
    assert agency.auto_maintenance is False


async def test_update_logo_saves_the_url(db_session):
    from app.repositories import agency as agency_repo
    from app.services.agency import update_logo

    agency = await _agency(db_session)
    await update_logo(db_session, agency, "/api/v1/agencies/x/logo?v=abc")
    refreshed = await agency_repo.by_id(db_session, agency.id)
    assert refreshed.logo == "/api/v1/agencies/x/logo?v=abc"
