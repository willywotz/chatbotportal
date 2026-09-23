"""Tests for app.features.agency.routers — create honours the lifecycle gate.

A fresh agency may only be created in a state reachable from `draft`: `draft`,
`disabled` or `active`. Creating straight into `maintenance` must be refused,
since `draft -> maintenance` is not a legal transition.
"""

import uuid

import pytest

from app.core.errors import ApiError
from app.core.security.principal import Principal
from app.features.agency import routers as agencies_router
from app.features.agency.schemas.agency import AgencyCreate


async def _admin(email="admin@example.com"):
    return Principal(id=str(uuid.uuid4()), email=email, display_name=None, role="admin", scopes=frozenset())


@pytest.mark.asyncio
async def test_create_agency_with_draft_status(db_session):
    admin = await _admin()
    res = await agencies_router.create_agency(
        body=AgencyCreate(
            name="as",
            short_name="a",
            connection_type="API",
            status="draft",
            endpoint_url="https://usecase.example/dopa/chat",
        ),
        session=db_session,
        _=admin,
    )
    assert res.status == "draft"


@pytest.mark.asyncio
async def test_create_agency_accepts_states_reachable_from_draft(db_session):
    admin = await _admin()
    for i, st in enumerate(("draft", "disabled", "active")):
        res = await agencies_router.create_agency(
            body=AgencyCreate(name=f"agency-{i}", short_name="a", status=st),
            session=db_session,
            _=admin,
        )
        assert res.status == st


@pytest.mark.asyncio
async def test_create_agency_refuses_maintenance(db_session):
    admin = await _admin()
    with pytest.raises(ApiError):
        await agencies_router.create_agency(
            body=AgencyCreate(name="x-maintenance", short_name="a", status="maintenance"),
            session=db_session,
            _=admin,
        )
