"""Tests for the event-driven core: outbox publish + dispatcher + a consumer."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agency import AgencyStatus
from app.models.audit import AuditLog
from app.models.event import DomainEvent
from app.repositories import agency as agency_repo
from app.services import event_consumers, events
from app.services.agency_lifecycle import transition_status
from app.services.event_consumers import register_consumers

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_own_session(db_session, monkeypatch):
    """dispatch_pending and the consumer each open their own short-lived
    session; bind both to the test's connection so their writes are visible
    through db_session."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(events, "AsyncSessionLocal", factory)
    monkeypatch.setattr(event_consumers, "AsyncSessionLocal", factory)


async def test_publish_appends_to_outbox_undispatched(db_session):
    event = await events.publish(db_session, "thing.happened", {"a": 1})
    await db_session.flush()
    assert event.dispatched_at is None
    count = (await db_session.execute(
        select(DomainEvent).where(DomainEvent.dispatched_at.is_(None))
    )).scalars().all()
    assert len(count) == 1


async def test_dispatch_pending_delivers_and_marks_dispatched(db_session):
    seen: list[dict] = []

    async def handler(payload: dict) -> None:
        seen.append(payload)

    events.subscribe("thing.happened", handler)
    await events.publish(db_session, "thing.happened", {"a": 1})
    await db_session.flush()

    handled = await events.dispatch_pending()

    assert handled == 1
    assert seen == [{"a": 1}]
    pending = (await db_session.execute(
        select(DomainEvent).where(DomainEvent.dispatched_at.is_(None))
    )).scalars().all()
    assert len(pending) == 0
    # A second run has nothing left to do (at-most-once).
    assert await events.dispatch_pending() == 0


async def test_failing_handler_does_not_block_the_row(db_session):
    async def boom(_payload: dict) -> None:
        raise RuntimeError("nope")

    events.subscribe("thing.boom", boom)
    await events.publish(db_session, "thing.boom", {})
    await db_session.flush()

    assert await events.dispatch_pending() == 1  # logged, not retried
    pending = (await db_session.execute(
        select(DomainEvent).where(DomainEvent.dispatched_at.is_(None))
    )).scalars().all()
    assert len(pending) == 0


async def test_agency_status_change_is_event_driven_end_to_end(db_session):
    register_consumers()
    agency = await agency_repo.create(
        db_session,
        name="A", short_name="A", connection_type="API", status=AgencyStatus.maintenance, auto_maintenance=True,
    )
    await db_session.flush()

    old = await transition_status(db_session, agency, "active")
    await db_session.flush()
    assert old == "maintenance"

    # Producer only wrote the outbox — the consumer has not run yet.
    pending = (await db_session.execute(
        select(DomainEvent).where(
            DomainEvent.event_type == "agency.status_changed", DomainEvent.dispatched_at.is_(None),
        )
    )).scalars().all()
    assert len(pending) == 1
    audit_rows = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "agency.status_changed")
    )).scalars().all()
    assert len(audit_rows) == 0

    await events.dispatch_pending()

    row = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "agency.status_changed")
    )).scalars().one()
    assert row.actor_email == "system:events"
    assert row.detail == {"from": "maintenance", "to": "active"}
