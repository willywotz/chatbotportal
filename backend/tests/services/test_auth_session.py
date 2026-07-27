import pytest

from app.services.auth_session import (
    _InProcessSessions, create_session, delete_session, remaining_ttl, resolve_session,
)


def test_inprocess_set_get_delete_and_expiry():
    clock = {"t": 1000.0}
    store = _InProcessSessions(now_fn=lambda: clock["t"])
    store.set("s1", "u1", ttl=100)
    assert store.get("s1") == "u1"
    assert 0 < store.ttl("s1") <= 100
    clock["t"] += 101            # advance past ttl
    assert store.get("s1") is None
    assert store.ttl("s1") is None
    store.set("s2", "u2", ttl=100)
    store.delete("s2")
    assert store.get("s2") is None


@pytest.mark.asyncio
async def test_module_roundtrip_uses_inprocess_when_no_redis(monkeypatch):
    # REDIS_URL is empty in tests -> in-process backend.
    sid = await create_session("user-123")
    assert await resolve_session(sid) == "user-123"
    assert (await remaining_ttl(sid)) > 0
    await delete_session(sid)
    assert await resolve_session(sid) is None
