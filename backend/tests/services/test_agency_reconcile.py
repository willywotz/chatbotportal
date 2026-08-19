from datetime import timedelta

import pytest

from app.models.agency import Agency
from app.models.connection_log import ConnectionLog
from app.utils import now

pytestmark = pytest.mark.asyncio


async def _agency(session, **fields):
    ag = Agency(name=fields.pop("name", "A"), short_name=fields.pop("short_name", "A"),
                connection_type="API", **fields)
    session.add(ag)
    await session.flush()
    return ag


async def _logs(session, ag, statuses, ago_minutes=1):
    session.add_all([
        ConnectionLog(agency_id=ag.id, connection_type="API", status=s,
                      created_at=now() - timedelta(minutes=ago_minutes))
        for s in statuses
    ])
    await session.flush()


async def _refresh(session, agency_id):
    from app.repositories import agency as agency_repo
    return await agency_repo.by_id(session, agency_id)


async def test_active_to_maintenance_when_error_over_50(db_session):
    from app.services.agency_reconcile import reconcile_statuses

    ag = await _agency(db_session, status="active")
    await _logs(db_session, ag, ["error", "error", "error", "error", "success"])  # 80% error, 5 checks
    await reconcile_statuses(db_session)
    refreshed = await _refresh(db_session, ag.id)
    assert refreshed.status == "maintenance"
    assert refreshed.auto_maintenance is True


async def test_no_flip_when_fewer_than_5_checks(db_session):
    from app.services.agency_reconcile import reconcile_statuses

    ag = await _agency(db_session, status="active")
    await _logs(db_session, ag, ["error", "error", "error", "error"])  # 100% error but only 4 checks
    await reconcile_statuses(db_session)
    assert (await _refresh(db_session, ag.id)).status == "active"


async def test_no_flip_at_exactly_50(db_session):
    from app.services.agency_reconcile import reconcile_statuses

    ag = await _agency(db_session, status="active")
    await _logs(db_session, ag, ["error", "error", "error", "success", "success", "success"])  # 50%, 6 checks
    await reconcile_statuses(db_session)
    assert (await _refresh(db_session, ag.id)).status == "active"


async def test_auto_maintenance_back_to_active_when_error_under_50(db_session):
    from app.services.agency_reconcile import reconcile_statuses

    ag = await _agency(db_session, status="maintenance", auto_maintenance=True)
    await _logs(db_session, ag, ["success", "success", "success", "success", "error"])  # 20% error, 5 checks
    await reconcile_statuses(db_session)
    refreshed = await _refresh(db_session, ag.id)
    assert refreshed.status == "active"
    assert refreshed.auto_maintenance is False


async def test_human_set_maintenance_not_reactivated(db_session):
    from app.services.agency_reconcile import reconcile_statuses

    ag = await _agency(db_session, status="maintenance", auto_maintenance=False)
    await _logs(db_session, ag, ["success"] * 5)  # 0% error
    await reconcile_statuses(db_session)
    assert (await _refresh(db_session, ag.id)).status == "maintenance"


async def test_draft_and_disabled_untouched(db_session):
    from app.services.agency_reconcile import reconcile_statuses

    draft = await _agency(db_session, name="D", short_name="D", status="draft")
    disabled = await _agency(db_session, name="Z", short_name="Z", status="disabled")
    await _logs(db_session, draft, ["error"] * 5)
    await _logs(db_session, disabled, ["error"] * 5)
    await reconcile_statuses(db_session)
    assert (await _refresh(db_session, draft.id)).status == "draft"
    assert (await _refresh(db_session, disabled.id)).status == "disabled"


async def test_reconcile_ignores_pre_reset_failures(db_session):
    from app.services.agency_reconcile import reconcile_statuses

    ag = await _agency(db_session, status="active", stats_reset_at=now() - timedelta(minutes=30))
    # 5 failures all BEFORE the reset baseline -> must be ignored
    await _logs(db_session, ag, ["error"] * 5, ago_minutes=120)
    await reconcile_statuses(db_session)
    assert (await _refresh(db_session, ag.id)).status == "active"


async def test_reconcile_still_flips_on_post_reset_failures(db_session):
    from app.services.agency_reconcile import reconcile_statuses

    ag = await _agency(db_session, status="active", stats_reset_at=now() - timedelta(hours=2))
    # 5 failures AFTER the reset baseline -> still trips
    await _logs(db_session, ag, ["error"] * 5, ago_minutes=30)
    await reconcile_statuses(db_session)
    refreshed = await _refresh(db_session, ag.id)
    assert refreshed.status == "maintenance"
    assert refreshed.auto_maintenance is True
