import pytest

from app.errors import ApiError
from app.models import Agency
from app.models.user import User
from app.routers import agencies as r
from app.schemas.agency import StatusUpdateRequest


async def _admin():
    return await User.create(email="a@e.com", hashed_password="x", role="admin", is_active=True)


@pytest.mark.asyncio
async def test_status_legal_transition(db):
    admin = await _admin()
    ag = await Agency.create(name="A", short_name="A", connection_type="API", status="active")
    res = await r.update_agency_status(ag.id, StatusUpdateRequest(status="maintenance"), user=admin)
    assert res.status == "maintenance"


@pytest.mark.asyncio
async def test_status_illegal_transition_422(db):
    admin = await _admin()
    ag = await Agency.create(name="A", short_name="A", connection_type="API", status="active")
    with pytest.raises(ApiError) as exc:
        await r.update_agency_status(ag.id, StatusUpdateRequest(status="draft"), user=admin)
    assert exc.value.status == 422
    assert "transition" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_status_404(db):
    import uuid
    admin = await _admin()
    with pytest.raises(ApiError) as exc:
        await r.update_agency_status(uuid.uuid4(), StatusUpdateRequest(status="active"), user=admin)
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_manual_status_change_clears_auto_maintenance(db):
    admin = await _admin()
    ag = await Agency.create(
        name="A", short_name="A", connection_type="API",
        status="maintenance", auto_maintenance=True,
    )
    await r.update_agency_status(ag.id, StatusUpdateRequest(status="active"), user=admin)
    refreshed = await Agency.get(id=ag.id)
    assert refreshed.auto_maintenance is False


@pytest.mark.asyncio
async def test_draft_to_active_blocked_without_conformance(db):
    from app.errors import ApiError
    admin = await _admin()
    ag = await Agency.create(name="A", short_name="A", connection_type="API", status="draft")
    with pytest.raises(ApiError) as exc:
        await r.update_agency_status(ag.id, StatusUpdateRequest(status="active"), user=admin)
    assert exc.value.code == "invalid_request"
    assert "conformance" in exc.value.message


@pytest.mark.asyncio
async def test_draft_to_active_allowed_with_passing_conformance(db):
    admin = await _admin()
    ag = await Agency.create(
        name="A", short_name="A", connection_type="API", status="draft",
        conformance_report={"passed": True, "checks": []},
    )
    res = await r.update_agency_status(ag.id, StatusUpdateRequest(status="active"), user=admin)
    assert res.status == "active"
