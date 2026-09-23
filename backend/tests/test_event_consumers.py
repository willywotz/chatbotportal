"""`_on_agency_status_changed` opens its own session (dispatcher only passes payload)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models.audit import AuditLog
from app.core import event_consumers


async def test_on_agency_status_changed_writes_audit_row(db_session, monkeypatch):
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(event_consumers, "AsyncSessionLocal", factory)

    await event_consumers._on_agency_status_changed(
        {"agency_id": "abc-123", "from": "draft", "to": "active"},
    )

    row = (await db_session.execute(select(AuditLog))).scalars().one()
    assert row.actor_email == "system:events"
    assert row.action == "agency.status_changed"
    assert row.object_type == "agency"
    assert row.object_id == "abc-123"
    assert row.detail == {"from": "draft", "to": "active"}


def test_register_consumers_is_idempotent(monkeypatch):
    from app.core import events

    monkeypatch.setattr(event_consumers, "_registered", False)
    monkeypatch.setattr(events, "_HANDLERS", {})

    event_consumers.register_consumers()
    event_consumers.register_consumers()

    assert len(events._HANDLERS["agency.status_changed"]) == 1
