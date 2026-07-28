"""Popular Questions API — anonymous public read, admin-gated writes.

SQLite-portable (db fixture). Auth is mocked via dependency_overrides,
mirroring tests/routers/test_llm_admin.py.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.security import generate_api_key, hash_api_key
from app.main import app
from app.models import Agency
from app.models.popular_question import PopularQuestion
from app.models.user import User, UserAPIKey

_PUBLIC = "/api/v1/public/popular-questions"
_ADMIN = "/api/v1/popular-questions"


def _admin():
    return User(id=uuid.uuid4(), email="admin@x.io", role="admin")


def _plain_user():
    return User(id=uuid.uuid4(), email="user@x.io", role="user")


async def _client(user=None):
    if user is not None:
        app.dependency_overrides[get_current_user] = user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.usefixtures("db")
async def test_public_get_works_without_auth():
    await PopularQuestion.create(text="q1", text_key="q1", source="seed")
    async with await _client() as c:
        r = await c.get(_PUBLIC)
    assert r.status_code == 200
    assert r.json()["data"][0]["text"] == "q1"


@pytest.mark.usefixtures("db")
@pytest.mark.parametrize("role", ["user", "viewer", "auditor"])
async def test_public_get_allowed_for_authenticated_read_only_roles(role):
    """Regression: the role allowlist chokepoint must not 403 a public GET.

    The frontend calls this from the authenticated chat page with an API key
    attached — it must not be blocked for user/viewer/auditor, none of whom
    are otherwise allowlisted for this path.
    """
    await PopularQuestion.create(text="q1", text_key="q1", source="seed")
    user = await User.create(email=f"pub-{role}@x.io", hashed_password="h", role=role)
    raw = generate_api_key()
    await UserAPIKey.create(user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12])
    async with await _client() as c:
        r = await c.get(_PUBLIC, headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200
    assert r.json()["data"][0]["text"] == "q1"


@pytest.mark.usefixtures("db")
async def test_admin_list_requires_auth():
    async with await _client() as c:
        r = await c.get(_ADMIN)
    assert r.status_code == 401


@pytest.mark.usefixtures("db")
async def test_admin_create_forbidden_for_plain_user():
    async with await _client(_plain_user) as c:
        r = await c.post(_ADMIN, json={"text": "new question"})
    app.dependency_overrides.clear()
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_admin_create_ok():
    async with await _client(_admin) as c:
        r = await c.post(_ADMIN, json={"text": "คำถามใหม่"})
    app.dependency_overrides.clear()
    assert r.status_code == 201
    body = r.json()
    assert body["text"] == "คำถามใหม่"
    assert body["source"] == "manual"


@pytest.mark.usefixtures("db")
async def test_admin_list_includes_hidden():
    await PopularQuestion.create(text="hidden one", text_key="hidden_one", source="seed", hidden=True)
    async with await _client(_admin) as c:
        r = await c.get(_ADMIN)
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["total"] == 1


@pytest.mark.usefixtures("db")
async def test_editing_auto_text_flips_source_to_manual():
    pq = await PopularQuestion.create(text="auto q", text_key="auto_q", source="auto")
    async with await _client(_admin) as c:
        r = await c.patch(f"{_ADMIN}/{pq.id}", json={"text": "edited auto q"})
    app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "manual"
    assert body["text"] == "edited auto q"

    stored = await PopularQuestion.get(id=pq.id)
    assert stored.source == "manual"
    assert stored.text_key == "edited auto q"


@pytest.mark.usefixtures("db")
async def test_editing_without_text_change_keeps_source():
    pq = await PopularQuestion.create(text="auto q2", text_key="auto_q2", source="auto")
    async with await _client(_admin) as c:
        r = await c.patch(f"{_ADMIN}/{pq.id}", json={"pinned": True})
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["source"] == "auto"
    assert r.json()["pinned"] is True


@pytest.mark.usefixtures("db")
async def test_delete_requires_admin():
    pq = await PopularQuestion.create(text="to delete", text_key="to_delete", source="manual")
    async with await _client(_plain_user) as c:
        r = await c.delete(f"{_ADMIN}/{pq.id}")
    app.dependency_overrides.clear()
    assert r.status_code == 403
    assert await PopularQuestion.filter(id=pq.id).exists()


@pytest.mark.usefixtures("db")
async def test_delete_ok():
    pq = await PopularQuestion.create(text="to delete2", text_key="to_delete2", source="manual")
    async with await _client(_admin) as c:
        r = await c.delete(f"{_ADMIN}/{pq.id}")
    app.dependency_overrides.clear()
    assert r.status_code == 204
    assert not await PopularQuestion.filter(id=pq.id).exists()


@pytest.mark.usefixtures("db")
async def test_regenerate_returns_202(monkeypatch):
    mock_regen = AsyncMock(return_value=0)
    monkeypatch.setattr("app.routers.popular_questions.regenerate", mock_regen)
    async with await _client(_admin) as c:
        r = await c.post(f"{_ADMIN}/regenerate")
    app.dependency_overrides.clear()
    assert r.status_code == 202


@pytest.mark.usefixtures("db")
async def test_create_resolves_agency():
    ag = await Agency.create(name="กรมการปกครอง")
    async with await _client(_admin) as c:
        r = await c.post(_ADMIN, json={"text": "ถามเรื่องบัตร", "agency_id": str(ag.id)})
    app.dependency_overrides.clear()
    assert r.status_code == 201
    assert r.json()["agency"]["id"] == str(ag.id)
