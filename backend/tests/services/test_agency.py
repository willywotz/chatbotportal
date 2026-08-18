import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.errors import ApiError


@pytest.mark.asyncio
async def test_parse_spec_raises_on_http_error():
    from app.services.agency import parse_spec
    from app.services.llm import LlmError

    with patch("app.services.llm.chat", AsyncMock(side_effect=LlmError("parse_spec: provider returned 429", status=429))):
        with pytest.raises(LlmError):
            await parse_spec("some spec text")


@pytest.mark.asyncio
async def test_get_agency_or_404_raises_for_missing_agency(db):
    from app.services.agency import get_agency_or_404

    with pytest.raises(ApiError) as exc:
        await get_agency_or_404(uuid.uuid4())
    assert exc.value.status == 404
    assert exc.value.message == "Agency not found"


@pytest.mark.asyncio
async def test_get_agency_or_404_returns_the_agency(db):
    from app.models import Agency
    from app.services.agency import get_agency_or_404

    created = await Agency.create(name="A", short_name="A", connection_type="API")
    found = await get_agency_or_404(created.id)
    assert found.id == created.id


@pytest.mark.asyncio
async def test_list_agencies_filters_by_status_connection_and_search(db):
    from app.models import Agency
    from app.services.agency import list_agencies

    await Agency.create(name="DOPA", short_name="d", connection_type="API", status="active")
    await Agency.create(name="MOI", short_name="m", connection_type="MCP", status="draft")

    all_agencies, total = await list_agencies(status_filter="all", connection_type=None, search=None)
    assert total == 2
    assert len(all_agencies) == 2

    active_only, active_total = await list_agencies(status_filter="active", connection_type=None, search=None)
    assert active_total == 1
    assert active_only[0].name == "DOPA"

    mcp_only, mcp_total = await list_agencies(status_filter="all", connection_type="mcp", search=None)
    assert mcp_total == 1
    assert mcp_only[0].name == "MOI"

    searched, searched_total = await list_agencies(status_filter="all", connection_type=None, search="dop")
    assert searched_total == 1
    assert searched[0].name == "DOPA"


@pytest.mark.asyncio
async def test_create_agency_persists_endpoints_and_headers(db):
    from app.schemas.agency import AgencyCreate
    from app.services.agency import create_agency

    body = AgencyCreate(
        name="A", short_name="a", connection_type="API", status="draft",
        api_endpoints=[{"method": "GET", "path": "/x", "description": "d"}],
        api_headers=[{"name": "X", "value": "1", "description": ""}],
    )
    agency = await create_agency(body)
    assert agency.id is not None
    assert agency.api_endpoints == [{"method": "GET", "path": "/x", "description": "d"}]
    assert agency.api_headers == [{"name": "X", "value": "1", "description": ""}]


@pytest.mark.asyncio
async def test_replace_agency_overwrites_fields(db):
    from app.models import Agency
    from app.schemas.agency import AgencyCreate
    from app.services.agency import replace_agency

    agency = await Agency.create(name="old", short_name="o", connection_type="API")
    body = AgencyCreate(name="new", short_name="n", connection_type="MCP")
    updated = await replace_agency(agency, body)
    assert updated.name == "new"
    assert updated.connection_type == "MCP"


@pytest.mark.asyncio
async def test_update_agency_demotes_active_agency_on_connection_identity_change(db):
    from app.models import Agency
    from app.schemas.agency import AgencyUpdate
    from app.services.agency import update_agency

    agency = await Agency.create(
        name="A", short_name="A", connection_type="API", status="active",
        endpoint_url="https://old.example.com", conformance_report={"passed": True, "checks": []},
    )
    updated = await update_agency(agency, AgencyUpdate(endpoint_url="https://new.example.com"))
    assert updated.status == "draft"
    assert updated.conformance_report is None


@pytest.mark.asyncio
async def test_delete_agency_removes_the_row(db):
    from app.models import Agency
    from app.services.agency import delete_agency

    agency = await Agency.create(name="A", short_name="A", connection_type="API")
    await delete_agency(agency)
    assert await Agency.get_or_none(id=agency.id) is None


@pytest.mark.asyncio
async def test_increment_calls_persists_the_counter(db):
    from app.models import Agency
    from app.services.agency import increment_calls

    agency = await Agency.create(name="A", short_name="A", connection_type="API", total_calls=1)
    updated = await increment_calls(agency)
    assert updated.total_calls == 2
    refreshed = await Agency.get(id=agency.id)
    assert refreshed.total_calls == 2


@pytest.mark.asyncio
async def test_increment_calls_is_atomic_across_stale_objects(db):
    from app.models import Agency
    from app.services.agency import increment_calls

    created = await Agency.create(name="A", short_name="A", connection_type="API", total_calls=0)
    # Two separately loaded objects, both stale at total_calls=0. A read-modify-
    # write loses one update; the atomic SQL add must land both.
    first = await Agency.get(id=created.id)
    second = await Agency.get(id=created.id)
    await increment_calls(first)
    await increment_calls(second)
    refreshed = await Agency.get(id=created.id)
    assert refreshed.total_calls == 2
    assert second.total_calls == 2  # refresh_from_db keeps the object readable


@pytest.mark.asyncio
async def test_run_connection_test_logs_a_connection_log_row(db):
    from app.models import Agency, ConnectionLog
    from app.services.agency import run_connection_test

    agency = await Agency.create(name="A", short_name="A", connection_type="API", endpoint_url="https://x.example")
    fake_result = {"success": True, "protocol": "REST API", "version": "-", "steps": [], "latency": "12ms", "statusCode": 200}
    with patch("app.services.agency.test_connection", AsyncMock(return_value=fake_result)):
        raw = await run_connection_test(agency)
    assert raw["success"] is True
    logs = await ConnectionLog.filter(agency_id=agency.id)
    assert len(logs) == 1
    assert logs[0].latency_ms == 12


@pytest.mark.asyncio
async def test_run_connection_test_recovers_auto_maintenance(db):
    from app.models import Agency
    from app.services.agency import run_connection_test

    agency = await Agency.create(
        name="A", short_name="A", connection_type="API", endpoint_url="https://x.example",
        status="maintenance", auto_maintenance=True,
    )
    fake_result = {"success": True, "protocol": "REST API", "version": "-", "steps": [], "latency": "5ms", "statusCode": 200}
    with patch("app.services.agency.test_connection", AsyncMock(return_value=fake_result)):
        await run_connection_test(agency)
    assert agency.status == "active"
    assert agency.auto_maintenance is False


@pytest.mark.asyncio
async def test_update_logo_saves_the_url(db):
    from app.models import Agency
    from app.services.agency import update_logo

    agency = await Agency.create(name="A", short_name="A", connection_type="API")
    await update_logo(agency, "/api/v1/agencies/x/logo?v=abc")
    refreshed = await Agency.get(id=agency.id)
    assert refreshed.logo == "/api/v1/agencies/x/logo?v=abc"
