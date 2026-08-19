import pytest

from app.errors import ApiError
from app.models.agency import AgencyStatus
from app.repositories import agency as agency_repo
from app.services.agency_lifecycle import LEGAL_TRANSITIONS, is_legal_transition, transition_status


def test_legal_transition_matrix():
    assert LEGAL_TRANSITIONS["draft"] == ["active", "disabled"]
    assert LEGAL_TRANSITIONS["active"] == ["maintenance", "disabled"]
    assert LEGAL_TRANSITIONS["maintenance"] == ["active", "disabled"]
    assert LEGAL_TRANSITIONS["disabled"] == ["active"]


def test_is_legal_transition():
    assert is_legal_transition("draft", "active") is True
    assert is_legal_transition("disabled", "maintenance") is False
    assert is_legal_transition("active", "draft") is False


async def test_transition_status_rejects_illegal_transition(db_session):
    agency = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API", status=AgencyStatus.active,
    )
    await db_session.flush()
    with pytest.raises(ApiError) as exc:
        await transition_status(db_session, agency, "draft")
    assert exc.value.status == 422


async def test_transition_status_blocks_draft_to_active_without_passing_conformance(db_session):
    agency = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API", status=AgencyStatus.draft,
    )
    await db_session.flush()
    with pytest.raises(ApiError) as exc:
        await transition_status(db_session, agency, "active")
    assert exc.value.code == "invalid_request"


async def test_transition_status_saves_and_clears_auto_maintenance(db_session):
    agency = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API",
        status=AgencyStatus.maintenance, auto_maintenance=True,
    )
    await db_session.flush()

    old_status = await transition_status(db_session, agency, "active")
    assert old_status == "maintenance"
    assert agency.status == "active"
    assert agency.auto_maintenance is False

    refreshed = await agency_repo.by_id(db_session, agency.id)
    assert refreshed.status == "active"
    assert refreshed.auto_maintenance is False
