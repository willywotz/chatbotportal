"""Tests for app.features.agency.routers — create honours the lifecycle gate.

A fresh agency may only be created in a state reachable from `draft` without a
conformance report: `draft` itself or `disabled`. Creating straight into
`active`/`maintenance` must be refused, so the conformance battery cannot be
skipped through the create endpoint.
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
    for i, st in enumerate(("draft", "disabled")):
        res = await agencies_router.create_agency(
            body=AgencyCreate(name=f"agency-{i}", short_name="a", status=st),
            session=db_session,
            _=admin,
        )
        assert res.status == st


@pytest.mark.asyncio
async def test_create_agency_refuses_ungated_activation(db_session):
    admin = await _admin()
    for st in ("active", "maintenance"):
        with pytest.raises(ApiError):
            await agencies_router.create_agency(
                body=AgencyCreate(name=f"x-{st}", short_name="a", status=st),
                session=db_session,
                _=admin,
            )
