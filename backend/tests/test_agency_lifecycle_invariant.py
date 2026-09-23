import pytest

from app.core.errors import ApiError
from app.features.agency.repositories import agency as agency_repo
from app.features.agency.schemas.agency import AgencyCreate
from app.features.agency.services import agency as agency_service


async def _active_agency(db_session, **overrides):
    fields = {
        "name": "Existing",
        "short_name": "EX",
        "connection_type": "API",
        "status": "active",
        "endpoint_url": "https://usecase.example/agency/chat",
    }
    fields.update(overrides)
    return await agency_repo.create(db_session, **fields)


@pytest.mark.asyncio
async def test_create_allows_draft(db_session):
    agency = await agency_service.create_agency(
        db_session, AgencyCreate(name="A", short_name="A", status="draft")
    )
    assert agency.status == "draft"


@pytest.mark.asyncio
async def test_create_allows_disabled(db_session):
    agency = await agency_service.create_agency(
        db_session, AgencyCreate(name="A", short_name="A", status="disabled")
    )
    assert agency.status == "disabled"


@pytest.mark.asyncio
async def test_create_allows_active(db_session):
    agency = await agency_service.create_agency(
        db_session, AgencyCreate(name="A", short_name="A", status="active")
    )
    assert agency.status == "active"


@pytest.mark.asyncio
async def test_create_rejects_maintenance(db_session):
    with pytest.raises(ApiError) as exc:
        await agency_service.create_agency(
            db_session, AgencyCreate(name="A", short_name="A", status="maintenance")
        )
    assert exc.value.status == 422


@pytest.mark.asyncio
async def test_create_rejects_unknown_status(db_session):
    with pytest.raises(ApiError) as exc:
        await agency_service.create_agency(
            db_session, AgencyCreate(name="A", short_name="A", status="banana")
        )
    assert exc.value.status == 422


@pytest.mark.asyncio
async def test_replace_same_status_is_noop(db_session):
    agency = await _active_agency(db_session)
    replaced = await agency_service.replace_agency(
        db_session,
        agency,
        AgencyCreate(name="Renamed", short_name="EX", connection_type="API",
                     status="active", endpoint_url="https://usecase.example/agency/chat"),
    )
    assert replaced.status == "active"
    assert replaced.name == "Renamed"


@pytest.mark.asyncio
async def test_replace_demotes_on_connection_identity_change(db_session):
    agency = await _active_agency(db_session)
    replaced = await agency_service.replace_agency(
        db_session,
        agency,
        AgencyCreate(name="Existing", short_name="EX", connection_type="API",
                     status="active", endpoint_url="https://usecase.example/agency/CHANGED"),
    )
    assert replaced.status == "draft"


@pytest.mark.asyncio
async def test_replace_activates_draft(db_session):
    agency = await agency_repo.create(
        db_session, name="Draft", short_name="DR", connection_type="API",
        status="draft", endpoint_url="https://usecase.example/agency/chat",
    )
    replaced = await agency_service.replace_agency(
        db_session,
        agency,
        AgencyCreate(name="Draft", short_name="DR", connection_type="API",
                     status="active", endpoint_url="https://usecase.example/agency/chat"),
    )
    assert replaced.status == "active"


@pytest.mark.asyncio
async def test_replace_rejects_illegal_active_to_draft(db_session):
    agency = await _active_agency(db_session)
    with pytest.raises(ApiError) as exc:
        await agency_service.replace_agency(
            db_session,
            agency,
            AgencyCreate(name="Existing", short_name="EX", connection_type="API",
                         status="draft", endpoint_url="https://usecase.example/agency/chat"),
        )
    assert exc.value.status == 422
