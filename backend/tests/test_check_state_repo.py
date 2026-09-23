import asyncio
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.agency.models.agency import Agency
from app.features.monitoring.models.check_state import AgencyCheckState
from app.features.monitoring.repositories import check_state as repo
from app.core.utils import now

pytestmark = pytest.mark.asyncio


async def test_ensure_states_creates_missing(db_session):
    a = Agency(name="Ensured", status="active")
    db_session.add(a)
    await db_session.flush()

    inserted = await repo.ensure_states(db_session, 300)
    await db_session.flush()

    st = await repo.get(db_session, a.id)
    assert st is not None and st.interval_seconds == 300
    assert inserted >= 1


async def test_claim_due_selects_due_and_bumps(db_session):
    a = Agency(name="Due", status="active")
    db_session.add(a)
    await db_session.flush()
    db_session.add(AgencyCheckState(agency_id=a.id, interval_seconds=300,
                                    next_check_at=now() - timedelta(seconds=1)))
    await db_session.flush()

    claimed = await repo.claim_due(db_session, batch=10, jitter_seconds=30)

    assert a.id in [c.agency_id for c in claimed]
    st = await repo.get(db_session, a.id)
    assert st.next_check_at > now()


async def test_claim_due_skips_disabled_and_not_due(db_session):
    disabled = Agency(name="Off", status="disabled")
    future = Agency(name="Later", status="active")
    db_session.add_all([disabled, future])
    await db_session.flush()
    db_session.add_all([
        AgencyCheckState(agency_id=disabled.id, interval_seconds=300, next_check_at=now() - timedelta(seconds=5)),
        AgencyCheckState(agency_id=future.id, interval_seconds=300, next_check_at=now() + timedelta(hours=1)),
    ])
    await db_session.flush()

    claimed = await repo.claim_due(db_session, batch=10, jitter_seconds=0)
    ids = [c.agency_id for c in claimed]
    assert disabled.id not in ids
    assert future.id not in ids


async def test_claim_due_is_disjoint_across_workers(_engine):
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed, seed.begin():
        a = Agency(name="Contended", status="active")
        seed.add(a)
        await seed.flush()
        seed.add(AgencyCheckState(agency_id=a.id, interval_seconds=300,
                                  next_check_at=now() - timedelta(seconds=1)))
        agency_id = a.id
    try:
        conn_a = await _engine.connect(); trans_a = await conn_a.begin()
        sess_a = AsyncSession(bind=conn_a, expire_on_commit=False)
        got_a = await repo.claim_due(sess_a, batch=10, jitter_seconds=0)
        async with factory() as sess_b, sess_b.begin():
            got_b = await repo.claim_due(sess_b, batch=10, jitter_seconds=0)
        ids_a = {c.agency_id for c in got_a}
        ids_b = {c.agency_id for c in got_b}
        assert agency_id in ids_a
        assert agency_id not in ids_b
        await sess_a.close(); await trans_a.rollback(); await conn_a.close()
    finally:
        async with factory() as cleanup, cleanup.begin():
            st = await cleanup.get(AgencyCheckState, agency_id)
            if st: await cleanup.delete(st)
            ag = await cleanup.get(Agency, agency_id)
            if ag: await cleanup.delete(ag)
