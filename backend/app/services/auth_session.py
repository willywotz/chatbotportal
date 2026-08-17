"""Opaque server-side session store backed by Postgres (Session model)."""
from datetime import timedelta

from app.config import settings
from app.models.session import Session
from app.utils import generate_uuid7, now


def _ttl_seconds() -> int:
    return settings.SESSION_TTL_MINUTES * 60


async def create_session(user_id: str) -> str:
    sid = generate_uuid7().hex
    await Session.create(id=sid, user_id=user_id, expires_at=now() + timedelta(seconds=_ttl_seconds()))
    return sid


async def resolve_session(session_id: str) -> str | None:
    session = await Session.get_or_none(id=session_id)
    if session is None:
        return None
    # withinlazy: lazy-delete only; add a periodic DELETE ... WHERE
    # expires_at <= now() reaper if the sessions table grows past a ceiling.
    if session.expires_at <= now():
        await session.delete()
        return None
    return str(session.user_id)


async def delete_session(session_id: str) -> None:
    await Session.filter(id=session_id).delete()


async def expire_session(session_id: str, ttl: int) -> None:
    """Reset a session's expiry to ``ttl`` seconds from now (rotation grace)."""
    await Session.filter(id=session_id).update(expires_at=now() + timedelta(seconds=ttl))


async def remaining_ttl(session_id: str) -> int | None:
    session = await Session.get_or_none(id=session_id)
    if session is None or session.expires_at <= now():
        return None
    return max(0, int((session.expires_at - now()).total_seconds()))
