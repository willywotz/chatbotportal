import pytest
from datetime import timedelta

from app.features.agency.models.agency import Agency
from app.features.monitoring.models.check_state import AgencyCheckState
from app.features.monitoring.services import incidents as svc
from app.features.monitoring.repositories import incident as incident_repo
from app.core.repositories import event as event_repo
from app.core.utils import now

pytestmark = pytest.mark.asyncio


async def _state(db_session, failures=0) -> AgencyCheckState:
    a = Agency(name="S", status="active")
    db_session.add(a)
    await db_session.flush()
    st = AgencyCheckState(agency_id=a.id, interval_seconds=300, next_check_at=now(),
                          consecutive_failures=failures)
    db_session.add(st)
    await db_session.flush()
    return st


async def test_opens_incident_on_threshold_and_publishes(db_session):
    st = await _state(db_session, failures=2)
    await svc.apply_transition(db_session, st, ok=False, detail="boom", failure_threshold=3)
    await db_session.flush()

    assert st.consecutive_failures == 3
    assert st.current_incident_id is not None
    assert await incident_repo.find_open(db_session, st.agency_id) is not None
    events = await event_repo.pending(db_session, 10)
    assert any(e.event_type == "agency.incident_opened" for e in events)


async def test_no_second_incident_while_open(db_session):
    st = await _state(db_session, failures=2)
    await svc.apply_transition(db_session, st, ok=False, detail="a", failure_threshold=3)
    first = st.current_incident_id
    await svc.apply_transition(db_session, st, ok=False, detail="b", failure_threshold=3)
    assert st.current_incident_id == first


async def test_recovery_closes_and_publishes(db_session):
    st = await _state(db_session, failures=2)
    await svc.apply_transition(db_session, st, ok=False, detail="boom", failure_threshold=3)
    await svc.apply_transition(db_session, st, ok=True, detail="ok", failure_threshold=3)
    await db_session.flush()

    assert st.consecutive_failures == 0
    assert st.current_incident_id is None
    assert await incident_repo.find_open(db_session, st.agency_id) is None
    events = await event_repo.pending(db_session, 10)
    assert any(e.event_type == "agency.incident_closed" for e in events)
