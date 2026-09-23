"""Verify that AgencyStatus no longer contains the legacy 'inactive' value."""

from app.features.agency.models.agency import AgencyStatus


def test_inactive_removed_from_agency_status():
    assert "inactive" not in [s.value for s in AgencyStatus]


def test_agency_status_has_expected_values():
    values = {s.value for s in AgencyStatus}
    assert values == {"draft", "active", "maintenance", "disabled"}
