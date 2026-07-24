"""The native history router moved from /api/v1/conversations to /api/v1/history
so an OpenAI-compatible router can later take the old prefix.
"""
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def test_history_prefix_serves_native_list_route():
    async with await _client() as c:
        r = await c.get("/api/v1/history")  # route exists (401/403 without auth, NOT 404)
    assert r.status_code != 404


async def test_old_conversations_list_path_is_gone():
    async with await _client() as c:
        r = await c.get("/api/v1/conversations")
    # Native list is gone; POST /conversations (OpenAI create) now owns the
    # path with no GET handler, so this is 405 Method Not Allowed rather than
    # a served list (or a bare 404).
    assert r.status_code == 405
