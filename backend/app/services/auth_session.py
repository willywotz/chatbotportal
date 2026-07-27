"""Opaque server-side session store for browser auth.

Sessions map an opaque id -> user_id with a TTL. Redis-backed when REDIS_URL is
set (shared across workers); an in-process fallback keeps single-worker dev
working without Redis, mirroring app/services/rate_limit.py's degradation.
"""
import time
import uuid

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.config import settings

_PREFIX = "session:"


class _InProcessSessions:
    """Per-process fallback store; monotonic-clock TTL. Injectable clock for tests."""

    def __init__(self, now_fn=time.monotonic):
        self._now = now_fn
        self._store: dict[str, tuple[str, float]] = {}

    def set(self, sid: str, user_id: str, *, ttl: int) -> None:
        self._store[sid] = (user_id, self._now() + ttl)

    def get(self, sid: str) -> str | None:
        item = self._store.get(sid)
        if item is None:
            return None
        user_id, expires_at = item
        if expires_at <= self._now():
            self._store.pop(sid, None)
            return None
        return user_id

    def delete(self, sid: str) -> None:
        self._store.pop(sid, None)

    def expire(self, sid: str, *, ttl: int) -> None:
        item = self._store.get(sid)
        if item is not None:
            self._store[sid] = (item[0], self._now() + ttl)

    def ttl(self, sid: str) -> int | None:
        item = self._store.get(sid)
        if item is None:
            return None
        remaining = int(item[1] - self._now())
        return remaining if remaining > 0 else None


class _RedisSessions:
    def __init__(self, client):
        self._c = client

    async def set(self, sid: str, user_id: str, *, ttl: int) -> None:
        await self._c.set(_PREFIX + sid, user_id, ex=ttl)

    async def get(self, sid: str) -> str | None:
        return await self._c.get(_PREFIX + sid)

    async def delete(self, sid: str) -> None:
        await self._c.delete(_PREFIX + sid)

    async def expire(self, sid: str, *, ttl: int) -> None:
        await self._c.expire(_PREFIX + sid, ttl)

    async def ttl(self, sid: str) -> int | None:
        t = await self._c.ttl(_PREFIX + sid)  # -2 no key, -1 no expiry
        return t if t is not None and t >= 0 else None


_inprocess = _InProcessSessions()
_redis: _RedisSessions | None = None


def _redis_backend() -> _RedisSessions | None:
    global _redis
    if not settings.REDIS_URL:
        return None
    if _redis is None:
        _redis = _RedisSessions(aioredis.from_url(settings.REDIS_URL, decode_responses=True))
    return _redis


def _ttl_seconds() -> int:
    return settings.SESSION_TTL_MINUTES * 60


async def create_session(user_id: str) -> str:
    sid = uuid.uuid4().hex
    ttl = _ttl_seconds()
    backend = _redis_backend()
    if backend is not None:
        try:
            await backend.set(sid, user_id, ttl=ttl)
            return sid
        except (RedisError, OSError):
            pass  # degrade to in-process
    _inprocess.set(sid, user_id, ttl=ttl)
    return sid


async def resolve_session(session_id: str) -> str | None:
    backend = _redis_backend()
    if backend is not None:
        try:
            return await backend.get(session_id)
        except (RedisError, OSError):
            pass
    return _inprocess.get(session_id)


async def delete_session(session_id: str) -> None:
    backend = _redis_backend()
    if backend is not None:
        try:
            await backend.delete(session_id)
            return
        except (RedisError, OSError):
            pass
    _inprocess.delete(session_id)


async def expire_session(session_id: str, ttl: int) -> None:
    """Reset a session's TTL to ``ttl`` seconds (used for rotation grace)."""
    backend = _redis_backend()
    if backend is not None:
        try:
            await backend.expire(session_id, ttl=ttl)
            return
        except (RedisError, OSError):
            pass
    _inprocess.expire(session_id, ttl=ttl)


async def remaining_ttl(session_id: str) -> int | None:
    backend = _redis_backend()
    if backend is not None:
        try:
            return await backend.ttl(session_id)
        except (RedisError, OSError):
            pass
    return _inprocess.ttl(session_id)
