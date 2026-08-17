"""Characterization + new-param tests for GET /conversations history listing.

SQLite-portable (db fixture). Auth is mocked via dependency_overrides.
"""
import uuid
from datetime import timedelta

import pytest

from app.auth.dependencies import get_current_user
from app.main import app
from app.models.conversation import Conversation
from app.models.user import User
from app.utils import now
from httpx import ASGITransport, AsyncClient


def _admin():
    u = User(id=uuid.uuid4(), email="a@x.io", role="admin", is_admin=True)
    return u


async def _client():
    app.dependency_overrides[get_current_user] = _admin
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.usefixtures("db")
async def test_history_returns_full_list_when_no_params():
    for i in range(3):
        await Conversation.create(title=f"t{i}", preview="p", status="success", message_count=2)
    async with await _client() as c:
        r = await c.get("/api/v1/history")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3                 # CURRENT behavior — pinned
    assert len(body["data"]) == 3


@pytest.mark.usefixtures("db")
async def test_history_search_filter_unchanged():
    await Conversation.create(title="visa renewal", preview="p", status="success", message_count=2)
    await Conversation.create(title="tax return", preview="p", status="success", message_count=2)
    async with await _client() as c:
        r = await c.get("/api/v1/history", params={"search": "visa"})
    app.dependency_overrides.clear()
    assert [d["title"] for d in r.json()["data"]] == ["visa renewal"]


@pytest.mark.usefixtures("db")
async def test_history_paginates_and_reports_full_total():
    for i in range(5):
        await Conversation.create(title=f"t{i}", preview="p", status="success", message_count=2)
    async with await _client() as c:
        r = await c.get("/api/v1/history", params={"page": 1, "page_size": 2})
    app.dependency_overrides.clear()
    body = r.json()
    assert len(body["data"]) == 2
    assert body["total"] == 5                 # full filtered count, not page length


@pytest.mark.usefixtures("db")
async def test_history_date_range_filters_in_query():
    old = await Conversation.create(title="old", preview="p", status="success", message_count=2)
    await Conversation.all().filter(id=old.id).update(created_at=now() - timedelta(days=10))
    await Conversation.create(title="new", preview="p", status="success", message_count=2)
    cutoff = (now() - timedelta(days=2)).strftime("%Y-%m-%d")
    async with await _client() as c:
        r = await c.get("/api/v1/history", params={"date_from": cutoff})
    app.dependency_overrides.clear()
    assert [d["title"] for d in r.json()["data"]] == ["new"]


@pytest.mark.usefixtures("db")
async def test_conversation_messages_expose_summary_fields():
    from app.models.conversation import Conversation, Message
    from app.routers.conversations import get_conversation_messages
    from unittest.mock import MagicMock

    conv = await Conversation.create(status="success")
    await Message.create(
        conversation=conv, role="assistant", content="a",
        summary="สรุป [1]",
        summary_references=[{"number": 1, "agency_id": "land", "agency_name": "กรมที่ดิน", "url": None}],
    )

    # MagicMock's `.is_admin` is a truthy Mock, so the ownership check
    # short-circuits and passes without needing to patch the check away.
    rows = await get_conversation_messages(conv.id, MagicMock())

    assert rows[0]["summary"] == "สรุป [1]"
    assert rows[0]["summary_references"][0]["number"] == 1
