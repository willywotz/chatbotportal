import pytest

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


@pytest.mark.asyncio
async def test_transition_status_rejects_illegal_transition(db):
    from app.errors import ApiError
    from app.models import Agency

    agency = await Agency.create(name="A", short_name="A", connection_type="API", status="active")
    with pytest.raises(ApiError) as exc:
        await transition_status(agency, "draft")
    assert exc.value.status == 422


@pytest.mark.asyncio
async def test_transition_status_blocks_draft_to_active_without_passing_conformance(db):
    from app.errors import ApiError
    from app.models import Agency

    agency = await Agency.create(name="A", short_name="A", connection_type="API", status="draft")
    with pytest.raises(ApiError) as exc:
        await transition_status(agency, "active")
    assert exc.value.code == "invalid_request"


@pytest.mark.asyncio
async def test_transition_status_saves_and_clears_auto_maintenance(db):
    from app.models import Agency

    agency = await Agency.create(
        name="A", short_name="A", connection_type="API", status="maintenance", auto_maintenance=True,
    )
    old_status = await transition_status(agency, "active")
    assert old_status == "maintenance"
    assert agency.status == "active"
    assert agency.auto_maintenance is False
    refreshed = await Agency.get(id=agency.id)
    assert refreshed.status == "active"
    assert refreshed.auto_maintenance is False
