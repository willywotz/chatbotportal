import uuid

import pytest

from app.core.security.principal import Principal
from app.features.agency import routers as r
from app.features.agency.schemas.agency import AgencyCreate


async def _admin():
    return Principal(id=str(uuid.uuid4()), email="a@e.com", display_name=None, role="admin", scopes=frozenset())


@pytest.mark.asyncio
async def test_create_persists_routing_fields_and_get_returns_health(db_session):
    admin = await _admin()
    created = await r.create_agency(
        body=AgencyCreate(name="RD", short_name="RD", connection_type="API",
                          status="active", priority=1, router_hint="ภาษี",
                          dispatch_timeout_s=30, mcp_tool_name=None),
        session=db_session,
        _=admin,
    )
    assert created.priority == 1
    assert created.router_hint == "ภาษี"
    assert created.dispatch_timeout_s == 30
    got = await r.get_agency(created.id, session=db_session)
    assert got.health is not None
    assert got.health.state == "unknown"  # no logs yet


@pytest.mark.asyncio
async def test_list_returns_health_and_accepts_lifecycle_filter(db_session):
    admin = await _admin()
    await r.create_agency(body=AgencyCreate(name="A", short_name="A", status="active"), session=db_session, _=admin)
    await r.create_agency(body=AgencyCreate(name="D", short_name="D", status="draft"), session=db_session, _=admin)
    res = await r.list_agencies(status_filter="all", connection_type=None, search=None, session=db_session)
    assert res.total == 2
    assert all(a.health is not None for a in res.data)
    drafts = await r.list_agencies(status_filter="draft", connection_type=None, search=None, session=db_session)
    assert {a.name for a in drafts.data} == {"D"}
