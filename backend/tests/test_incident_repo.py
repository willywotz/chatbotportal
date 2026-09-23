import pytest

from app.features.agency.models.agency import Agency
from app.features.monitoring.repositories import incident as repo

pytestmark = pytest.mark.asyncio


async def _agency(db_session) -> Agency:
    a = Agency(name="Inc", status="active")
    db_session.add(a)
    await db_session.flush()
    return a


async def test_open_then_find_then_close(db_session):
    a = await _agency(db_session)
    inc = await repo.open_incident(db_session, a.id, "timeout")
    assert inc.id is not None and inc.ended_at is None

    found = await repo.find_open(db_session, a.id)
    assert found is not None and found.id == inc.id

    await repo.close_incident(db_session, inc)
    assert inc.ended_at is not None
    assert await repo.find_open(db_session, a.id) is None


async def test_one_open_incident_invariant(db_session):
    from sqlalchemy.exc import IntegrityError
    a = await _agency(db_session)
    await repo.open_incident(db_session, a.id, "first")
    with pytest.raises(IntegrityError):
        await repo.open_incident(db_session, a.id, "second")
