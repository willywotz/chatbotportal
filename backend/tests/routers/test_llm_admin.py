"""Admin CRUD API for LLM providers, routes, and purposes.

SQLite-portable (db fixture). Auth is mocked via dependency_overrides, mirroring
tests/test_connection_logs_filter.py and tests/test_conversations_history.py.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.main import app
from app.models import LlmProvider, LlmRoute
from app.models.user import User
from app.routers.settings import MASK
from app.services.llm import KNOWN_PURPOSES

_PROVIDERS = "/api/v1/llm/providers"
_ROUTES = "/api/v1/llm/routes"
_PURPOSES = "/api/v1/llm/purposes"


def _admin():
    return User(id=uuid.uuid4(), email="admin@x.io", role="admin", is_admin=True)


def _plain_user():
    return User(id=uuid.uuid4(), email="user@x.io", role="user")


async def _client(user=None):
    app.dependency_overrides[get_current_user] = user or _admin
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _mock_httpx(json_body, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm), client


@pytest.mark.usefixtures("db")
async def test_create_provider_returns_masked_key():
    async with await _client() as c:
        r = await c.post(_PROVIDERS, json={
            "name": "openai", "base_url": "https://api.openai.com/v1/chat", "api_key": "sk-real-secret",
        })
    app.dependency_overrides.clear()
    assert r.status_code == 201
    body = r.json()
    assert body["api_key"] == MASK

    stored = await LlmProvider.get(id=body["id"])
    assert stored.api_key == "sk-real-secret"  # real key persisted, only the response is masked


@pytest.mark.usefixtures("db")
async def test_list_providers_masks_api_key():
    await LlmProvider.create(name="p1", base_url="https://p1.example", api_key="super-secret")
    async with await _client() as c:
        r = await c.get(_PROVIDERS)
    app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["data"][0]["api_key"] == MASK


@pytest.mark.usefixtures("db")
async def test_update_with_mask_keeps_stored_key():
    provider = await LlmProvider.create(name="p2", base_url="https://p2.example", api_key="original-key")
    async with await _client() as c:
        r = await c.patch(f"{_PROVIDERS}/{provider.id}", json={"api_key": MASK, "timeout_seconds": 30.0})
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["api_key"] == MASK

    stored = await LlmProvider.get(id=provider.id)
    assert stored.api_key == "original-key"      # unchanged
    assert stored.timeout_seconds == 30.0         # other fields still update


@pytest.mark.usefixtures("db")
async def test_update_with_null_api_key_keeps_stored_key():
    provider = await LlmProvider.create(name="p2b", base_url="https://p2b.example", api_key="original-key-2")
    async with await _client() as c:
        r = await c.patch(f"{_PROVIDERS}/{provider.id}", json={"api_key": None})
    app.dependency_overrides.clear()
    assert r.status_code == 200
    stored = await LlmProvider.get(id=provider.id)
    assert stored.api_key == "original-key-2"


@pytest.mark.usefixtures("db")
async def test_create_route_ok():
    provider = await LlmProvider.create(name="p3", base_url="https://p3.example")
    async with await _client() as c:
        r = await c.post(_ROUTES, json={
            "purpose": "classification", "provider_id": str(provider.id), "model": "gpt-x",
        })
    app.dependency_overrides.clear()
    assert r.status_code == 201
    body = r.json()
    assert body["provider_name"] == "p3"
    assert body["purpose"] == "classification"


@pytest.mark.usefixtures("db")
async def test_create_route_unknown_provider_404():
    async with await _client() as c:
        r = await c.post(_ROUTES, json={
            "purpose": "classification", "provider_id": str(uuid.uuid4()), "model": "gpt-x",
        })
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.usefixtures("db")
async def test_create_route_duplicate_purpose_409():
    provider = await LlmProvider.create(name="p4", base_url="https://p4.example")
    await LlmRoute.create(purpose="brief", provider=provider, model="gpt-x")
    async with await _client() as c:
        r = await c.post(_ROUTES, json={
            "purpose": "brief", "provider_id": str(provider.id), "model": "gpt-y",
        })
    app.dependency_overrides.clear()
    assert r.status_code == 409


@pytest.mark.usefixtures("db")
async def test_delete_provider_in_use_409():
    provider = await LlmProvider.create(name="p5", base_url="https://p5.example")
    await LlmRoute.create(purpose="judge", provider=provider, model="gpt-x")
    async with await _client() as c:
        r = await c.delete(f"{_PROVIDERS}/{provider.id}")
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert await LlmProvider.filter(id=provider.id).exists()


@pytest.mark.usefixtures("db")
async def test_non_admin_create_provider_403():
    async with await _client(_plain_user) as c:
        r = await c.post(_PROVIDERS, json={"name": "p6", "base_url": "https://p6.example"})
    app.dependency_overrides.clear()
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_list_purposes_returns_known_purposes():
    async with await _client() as c:
        r = await c.get(_PURPOSES)
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json() == {"data": list(KNOWN_PURPOSES)}
    assert len(r.json()["data"]) == 5


@pytest.mark.usefixtures("db")
async def test_create_route_invalid_purpose_422():
    provider = await LlmProvider.create(name="p8", base_url="https://p8.example")
    async with await _client() as c:
        r = await c.post(_ROUTES, json={
            "purpose": "nope", "provider_id": str(provider.id), "model": "gpt-x",
        })
    app.dependency_overrides.clear()
    assert r.status_code == 422


@pytest.mark.usefixtures("db")
async def test_create_route_valid_purpose_succeeds():
    provider = await LlmProvider.create(name="p9", base_url="https://p9.example")
    async with await _client() as c:
        r = await c.post(_ROUTES, json={
            "purpose": "popular_questions", "provider_id": str(provider.id), "model": "gpt-x",
        })
    app.dependency_overrides.clear()
    assert r.status_code == 201
    assert r.json()["purpose"] == "popular_questions"


@pytest.mark.usefixtures("db")
async def test_test_route_success():
    from app.services.llm import client as llm_client
    llm_client.invalidate()
    provider = await LlmProvider.create(name="pt", base_url="https://pt.example", api_key="k")
    await LlmRoute.create(purpose="classification", provider=provider, model="m1")
    body = {"model": "m1", "choices": [{"message": {"content": "pong"}}]}
    factory, _ = _mock_httpx(body)
    with patch.object(llm_client.httpx, "AsyncClient", factory):
        async with await _client() as c:
            r = await c.post(f"{_ROUTES}/classification/test")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is True
    assert out["model"] == "m1"
    assert out["latency_ms"] >= 0


@pytest.mark.usefixtures("db")
async def test_test_route_disabled_returns_ok_false():
    from app.services.llm import client as llm_client
    llm_client.invalidate()
    provider = await LlmProvider.create(name="pt2", base_url="https://pt2.example", api_key="k")
    await LlmRoute.create(purpose="brief", provider=provider, model="m", enabled=False)
    async with await _client() as c:
        r = await c.post(f"{_ROUTES}/brief/test")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is False
    assert "no enabled route" in out["error"]


@pytest.mark.usefixtures("db")
async def test_test_route_unknown_purpose_404():
    async with await _client() as c:
        r = await c.post(f"{_ROUTES}/nope/test")
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.usefixtures("db")
async def test_test_route_requires_admin():
    async with await _client(_plain_user) as c:
        r = await c.post(f"{_ROUTES}/classification/test")
    app.dependency_overrides.clear()
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_mutation_invalidates_route_cache(monkeypatch):
    mock_invalidate = MagicMock()
    monkeypatch.setattr("app.routers.llm.invalidate", mock_invalidate)
    async with await _client() as c:
        r = await c.post(_PROVIDERS, json={"name": "p7", "base_url": "https://p7.example"})
    app.dependency_overrides.clear()
    assert r.status_code == 201
    mock_invalidate.assert_called_once()
