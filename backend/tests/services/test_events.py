"""Tests for the event-driven core: outbox publish + dispatcher + a consumer."""
import pytest

from app.models.agency import Agency
from app.models.audit import AuditLog
from app.models.event import DomainEvent
from app.services import events
from app.services.agency_lifecycle import transition_status
from app.services.event_consumers import register_consumers


@pytest.mark.asyncio
async def test_publish_appends_to_outbox_undispatched(db):
    event = await events.publish("thing.happened", {"a": 1})
    assert event.dispatched_at is None
    assert await DomainEvent.filter(dispatched_at=None).count() == 1


@pytest.mark.asyncio
async def test_dispatch_pending_delivers_and_marks_dispatched(db):
    seen: list[dict] = []

    async def handler(payload: dict) -> None:
        seen.append(payload)

    events.subscribe("thing.happened", handler)
    await events.publish("thing.happened", {"a": 1})

    handled = await events.dispatch_pending()

    assert handled == 1
    assert seen == [{"a": 1}]
    assert await DomainEvent.filter(dispatched_at=None).count() == 0
    # A second run has nothing left to do (at-most-once).
    assert await events.dispatch_pending() == 0


@pytest.mark.asyncio
async def test_failing_handler_does_not_block_the_row(db):
    async def boom(_payload: dict) -> None:
        raise RuntimeError("nope")

    events.subscribe("thing.boom", boom)
    await events.publish("thing.boom", {})

    assert await events.dispatch_pending() == 1  # logged, not retried
    assert await DomainEvent.filter(dispatched_at=None).count() == 0


@pytest.mark.asyncio
async def test_agency_status_change_is_event_driven_end_to_end(db):
    register_consumers()
    agency = await Agency.create(
        name="A", short_name="A", connection_type="API", status="maintenance", auto_maintenance=True
    )

    old = await transition_status(agency, "active")
    assert old == "maintenance"

    # Producer only wrote the outbox — the consumer has not run yet.
    assert await DomainEvent.filter(event_type="agency.status_changed", dispatched_at=None).count() == 1
    assert await AuditLog.filter(action="agency.status_changed").count() == 0

    await events.dispatch_pending()

    row = await AuditLog.filter(action="agency.status_changed").first()
    assert row is not None
    assert row.actor_email == "system:events"
    assert row.detail == {"from": "maintenance", "to": "active"}
