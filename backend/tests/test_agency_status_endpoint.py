import uuid

import pytest

from app.auth.keycloak import Principal
from app.errors import ApiError
from app.models import Agency
from app.models.agency import AgencyStatus
from app.repositories import agency as agency_repo
from app.routers import agencies as r
from app.schemas.agency import StatusUpdateRequest


async def _admin():
    return Principal(id=str(uuid.uuid4()), email="a@e.com", display_name=None, role="admin", scopes=frozenset())


@pytest.mark.asyncio
async def test_status_legal_transition(db_session):
    admin = await _admin()
    ag = await agency_repo.create(db_session, name="A", short_name="A", connection_type="API", status=AgencyStatus.active)
    res = await r.update_agency_status(ag.id, StatusUpdateRequest(status="maintenance"), session=db_session, user=admin)
    assert res.status == "maintenance"


@pytest.mark.asyncio
async def test_status_illegal_transition_422(db_session):
    admin = await _admin()
    ag = await agency_repo.create(db_session, name="A", short_name="A", connection_type="API", status=AgencyStatus.active)
    with pytest.raises(ApiError) as exc:
        await r.update_agency_status(ag.id, StatusUpdateRequest(status=AgencyStatus.draft), session=db_session, user=admin)
    assert exc.value.status == 422
    assert "transition" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_status_404(db_session):
    admin = await _admin()
    with pytest.raises(ApiError) as exc:
        await r.update_agency_status(uuid.uuid4(), StatusUpdateRequest(status=AgencyStatus.active), session=db_session, user=admin)
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_manual_status_change_clears_auto_maintenance(db_session):
    admin = await _admin()
    ag = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API",
        status=AgencyStatus.maintenance, auto_maintenance=True,
    )
    await r.update_agency_status(ag.id, StatusUpdateRequest(status=AgencyStatus.active), session=db_session, user=admin)
    refreshed = await db_session.get(Agency, ag.id)
    assert refreshed.auto_maintenance is False


@pytest.mark.asyncio
async def test_draft_to_active_blocked_without_conformance(db_session):
    admin = await _admin()
    ag = await agency_repo.create(db_session, name="A", short_name="A", connection_type="API", status=AgencyStatus.draft)
    with pytest.raises(ApiError) as exc:
        await r.update_agency_status(ag.id, StatusUpdateRequest(status=AgencyStatus.active), session=db_session, user=admin)
    assert exc.value.code == "invalid_request"
    assert "conformance" in exc.value.message


@pytest.mark.asyncio
async def test_draft_to_active_allowed_with_passing_conformance(db_session):
    admin = await _admin()
    ag = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API", status=AgencyStatus.draft,
        conformance_report={"passed": True, "checks": []},
    )
    res = await r.update_agency_status(ag.id, StatusUpdateRequest(status=AgencyStatus.active), session=db_session, user=admin)
    assert res.status == "active"
