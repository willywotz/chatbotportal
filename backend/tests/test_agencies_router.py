"""Tests for app.routers.agencies — create with the new lifecycle states.

Regression net for the 500 raised when the redesigned frontend creates an
agency in the `draft` state: the AgencyStatus enum previously allowed only
active/inactive, so Tortoise's CharEnumField rejected `draft`/`maintenance`/
`disabled` on insert.
"""

import uuid

import pytest

from app.auth.keycloak import Principal
from app.routers import agencies as agencies_router
from app.schemas.agency import AgencyCreate


async def _admin(email="admin@example.com"):
    return Principal(id=str(uuid.uuid4()), email=email, display_name=None, role="admin", scopes=frozenset())


@pytest.mark.asyncio
async def test_create_agency_with_draft_status(db):
    admin = await _admin()
    res = await agencies_router.create_agency(
        body=AgencyCreate(
            name="as",
            short_name="a",
            connection_type="API",
            status="draft",
            endpoint_url="https://usecase.example/dopa/chat",
        ),
        _=admin,
    )
    assert res.status == "draft"


@pytest.mark.asyncio
async def test_create_agency_accepts_all_lifecycle_states(db):
    admin = await _admin()
    for i, st in enumerate(("draft", "active", "maintenance", "disabled")):
        res = await agencies_router.create_agency(
            body=AgencyCreate(name=f"agency-{i}", short_name="a", status=st),
            _=admin,
        )
        assert res.status == st
