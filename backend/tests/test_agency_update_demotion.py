"""Changing a connection-identity field on an active/maintenance agency must
demote it to draft and clear its conformance_report, atomically."""
import uuid

import pytest

from app.core.security.principal import Principal
from app.features.agency.models.agency import Agency
from app.features.agency.repositories import agency as agency_repo
from app.features.agency.routers import crud
from app.features.agency.schemas.agency import AgencyUpdate

_CONFORMANCE = {"passed": True, "checks": []}


async def _admin():
    return Principal(id=str(uuid.uuid4()), email="a@e.com", display_name=None, role="admin", scopes=frozenset())


async def _agency(session, **overrides):
    defaults = dict(
        name="A",
        short_name="A",
        connection_type="API",
        status="active",
        endpoint_url="https://old.example.com",
        conformance_report=_CONFORMANCE,
    )
    defaults.update(overrides)
    return await agency_repo.create(session, **defaults)


@pytest.mark.asyncio
async def test_active_endpoint_url_change_demotes_to_draft(db_session):
    admin = await _admin()
    ag = await _agency(db_session, status="active")
    res = await crud.update_agency(ag.id, AgencyUpdate(endpoint_url="https://new.example.com"), session=db_session, user=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert res.status == "draft"
    assert refreshed.conformance_report is None


@pytest.mark.asyncio
async def test_active_connection_type_change_demotes_to_draft(db_session):
    admin = await _admin()
    ag = await _agency(db_session, status="active")
    res = await crud.update_agency(ag.id, AgencyUpdate(connection_type="MCP"), session=db_session, user=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert res.status == "draft"
    assert refreshed.conformance_report is None


@pytest.mark.asyncio
async def test_active_api_headers_change_demotes_to_draft(db_session):
    admin = await _admin()
    ag = await _agency(db_session, status="active", api_headers=[{"name": "X", "value": "1", "description": ""}])
    res = await crud.update_agency(
        ag.id,
        AgencyUpdate(api_headers=[{"name": "X", "value": "2", "description": ""}]),
        session=db_session,
        user=admin,
    )
    refreshed = await db_session.get(Agency, ag.id)
    assert res.status == "draft"
    assert refreshed.conformance_report is None


@pytest.mark.asyncio
async def test_active_general_field_change_stays_active(db_session):
    admin = await _admin()
    ag = await _agency(db_session, status="active")
    res = await crud.update_agency(ag.id, AgencyUpdate(name="New Name"), session=db_session, user=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert res.status == "active"
    assert refreshed.conformance_report == _CONFORMANCE


@pytest.mark.asyncio
async def test_active_same_value_patch_stays_active(db_session):
    admin = await _admin()
    ag = await _agency(db_session, status="active", endpoint_url="https://same.example.com")
    res = await crud.update_agency(
        ag.id, AgencyUpdate(endpoint_url="https://same.example.com"), session=db_session, user=admin
    )
    refreshed = await db_session.get(Agency, ag.id)
    assert res.status == "active"
    assert refreshed.conformance_report == _CONFORMANCE


@pytest.mark.asyncio
async def test_maintenance_endpoint_url_change_demotes_to_draft(db_session):
    admin = await _admin()
    ag = await _agency(db_session, status="maintenance")
    res = await crud.update_agency(ag.id, AgencyUpdate(endpoint_url="https://new.example.com"), session=db_session, user=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert res.status == "draft"
    assert refreshed.conformance_report is None


@pytest.mark.asyncio
async def test_disabled_endpoint_url_change_stays_disabled(db_session):
    admin = await _admin()
    ag = await _agency(db_session, status="disabled")
    res = await crud.update_agency(ag.id, AgencyUpdate(endpoint_url="https://new.example.com"), session=db_session, user=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert res.status == "disabled"
    assert refreshed.conformance_report == _CONFORMANCE


@pytest.mark.asyncio
async def test_draft_endpoint_url_change_stays_draft(db_session):
    admin = await _admin()
    ag = await _agency(db_session, status="draft")
    res = await crud.update_agency(ag.id, AgencyUpdate(endpoint_url="https://new.example.com"), session=db_session, user=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert res.status == "draft"
    assert refreshed.conformance_report == _CONFORMANCE
