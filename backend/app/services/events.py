"""Event-driven core: a transactional outbox plus an in-process dispatcher.

A producer calls `publish(session, event_type, payload)`, which durably appends
a `DomainEvent` row (the outbox) inside the caller's own transaction. A
background dispatcher (`dispatch_pending`) opens its own short-lived session,
reads undispatched rows, delivers each to the handlers registered with
`subscribe`, then stamps the row `dispatched_at`. Producers never call
consumers directly.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.event import DomainEvent
from app.repositories import event as event_repo

logger = logging.getLogger(__name__)

Handler = Callable[[dict], Awaitable[None]]

_HANDLERS: dict[str, list[Handler]] = {}


def subscribe(event_type: str, handler: Handler) -> None:
    """Register an async consumer for an event type."""
    _HANDLERS.setdefault(event_type, []).append(handler)


async def publish(session: AsyncSession, event_type: str, payload: dict) -> DomainEvent:
    """Append a domain event to the outbox, in the caller's transaction."""
    return await event_repo.add(session, event_type, payload)


async def dispatch_pending(limit: int = 100) -> int:
    """Deliver undispatched events to their handlers; return the count handled.

    withinlazy: at-most-once per handler — a row is marked dispatched even if a
    handler raised (failure is logged, not retried). Add a retry count / dead-
    letter column if a consumer must not miss an event.
    """
    async with AsyncSessionLocal() as session, session.begin():
        rows = await event_repo.pending(session, limit)
        for event in rows:
            for handler in _HANDLERS.get(event.event_type, []):
                try:
                    await handler(event.payload)
                except Exception:
                    logger.exception("event handler failed for %s", event.event_type)
            await event_repo.mark_dispatched(session, event)
    return len(rows)
