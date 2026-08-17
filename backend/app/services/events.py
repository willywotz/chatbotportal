"""Event-driven core: a transactional outbox plus an in-process dispatcher.

A producer calls `publish(event_type, payload)`, which durably appends a
`DomainEvent` row (the outbox) — in the caller's DB transaction when there is
one. A background dispatcher (`dispatch_pending`) reads undispatched rows,
delivers each to the handlers registered with `subscribe`, then stamps the row
`dispatched_at`. Producers never call consumers directly.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.models.event import DomainEvent
from app.utils import now

logger = logging.getLogger(__name__)

Handler = Callable[[dict], Awaitable[None]]

_HANDLERS: dict[str, list[Handler]] = {}


def subscribe(event_type: str, handler: Handler) -> None:
    """Register an async consumer for an event type."""
    _HANDLERS.setdefault(event_type, []).append(handler)


async def publish(event_type: str, payload: dict) -> DomainEvent:
    """Append a domain event to the outbox."""
    return await DomainEvent.create(event_type=event_type, payload=payload)


async def dispatch_pending(limit: int = 100) -> int:
    """Deliver undispatched events to their handlers; return the count handled.

    withinlazy: at-most-once per handler — a row is marked dispatched even if a
    handler raised (failure is logged, not retried). Add a retry count / dead-
    letter column if a consumer must not miss an event.
    """
    rows = await DomainEvent.filter(dispatched_at=None).order_by("created_at").limit(limit)
    for event in rows:
        for handler in _HANDLERS.get(event.event_type, []):
            try:
                await handler(event.payload)
            except Exception:
                logger.exception("event handler failed for %s", event.event_type)
        event.dispatched_at = now()
        await event.save(update_fields=["dispatched_at"])
    return len(rows)
