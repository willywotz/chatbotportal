import pytest

from app.models import Agency
from app.repositories import agency as agency_repo
from app.utils import now


@pytest.mark.asyncio
async def test_stats_reset_at_defaults_to_none(db_session):
    ag = await agency_repo.create(db_session, name="A", short_name="A", connection_type="API", status="active")
    assert ag.stats_reset_at is None


@pytest.mark.asyncio
async def test_stats_reset_at_persists(db_session):
    ts = now()
    ag = await agency_repo.create(
        db_session, name="A", short_name="A", connection_type="API", status="active",
        stats_reset_at=ts,
    )
    refreshed = await db_session.get(Agency, ag.id)
    assert refreshed.stats_reset_at is not None
