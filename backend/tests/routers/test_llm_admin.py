"""Admin CRUD API for LLM providers, routes, and purposes."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.repositories import llm as llm_repo
from app.routers.settings import MASK
from app.services.llm import KNOWN_PURPOSES

_PROVIDERS = "/api/v1/language-model/providers"
_ROUTES = "/api/v1/language-model/routes"
_PURPOSES = "/api/v1/language-model/purposes"

_USER_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


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


async def test_create_provider_returns_masked_key(client, db_session, as_principal):
    as_principal()
    r = await client.post(_PROVIDERS, json={
        "name": "openai", "base_url": "https://api.openai.com/v1/chat", "api_key": "sk-real-secret",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["api_key"] == MASK

    stored = await llm_repo.get_provider(db_session, uuid.UUID(body["id"]))
    assert stored.api_key == "sk-real-secret"  # real key persisted, only the response is masked


async def test_list_providers_masks_api_key(client, db_session, as_principal):
    as_principal()
    await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example", api_key="super-secret")
    r = await client.get(_PROVIDERS)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["data"][0]["api_key"] == MASK


async def test_update_with_mask_keeps_stored_key(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p2", base_url="https://p2.example", api_key="original-key")
    r = await client.patch(f"{_PROVIDERS}/{provider.id}", json={"api_key": MASK, "timeout_seconds": 30.0})
    assert r.status_code == 200
    assert r.json()["api_key"] == MASK

    stored = await llm_repo.get_provider(db_session, provider.id)
    assert stored.api_key == "original-key"      # unchanged
    assert stored.timeout_seconds == 30.0         # other fields still update


async def test_update_with_null_api_key_keeps_stored_key(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p2b", base_url="https://p2b.example", api_key="original-key-2")
    r = await client.patch(f"{_PROVIDERS}/{provider.id}", json={"api_key": None})
    assert r.status_code == 200
    stored = await llm_repo.get_provider(db_session, provider.id)
    assert stored.api_key == "original-key-2"


async def test_create_route_ok(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p3", base_url="https://p3.example")
    r = await client.post(_ROUTES, json={
        "purpose": "classification", "provider_id": str(provider.id), "model": "gpt-x",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["provider_name"] == "p3"
    assert body["purpose"] == "classification"


async def test_create_route_unknown_provider_404(client, as_principal):
    as_principal()
    r = await client.post(_ROUTES, json={
        "purpose": "classification", "provider_id": str(uuid.uuid4()), "model": "gpt-x",
    })
    assert r.status_code == 404


async def test_create_route_duplicate_purpose_409(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p4", base_url="https://p4.example")
    await llm_repo.create_route(db_session, purpose="brief", provider_id=provider.id, model="gpt-x")
    r = await client.post(_ROUTES, json={
        "purpose": "brief", "provider_id": str(provider.id), "model": "gpt-y",
    })
    assert r.status_code == 409


async def test_delete_provider_in_use_409(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p5", base_url="https://p5.example")
    await llm_repo.create_route(db_session, purpose="judge", provider_id=provider.id, model="gpt-x")
    r = await client.delete(f"{_PROVIDERS}/{provider.id}")
    assert r.status_code == 409
    assert await llm_repo.get_provider(db_session, provider.id) is not None


async def test_non_admin_create_provider_403(client, as_principal):
    as_principal(role="user", scopes=_USER_SCOPES)
    r = await client.post(_PROVIDERS, json={"name": "p6", "base_url": "https://p6.example"})
    assert r.status_code == 403


async def test_list_purposes_returns_known_purposes(client, as_principal):
    as_principal()
    r = await client.get(_PURPOSES)
    assert r.status_code == 200
    assert r.json() == {"data": list(KNOWN_PURPOSES)}
    assert len(r.json()["data"]) == 5


async def test_create_route_invalid_purpose_422(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p8", base_url="https://p8.example")
    r = await client.post(_ROUTES, json={
        "purpose": "nope", "provider_id": str(provider.id), "model": "gpt-x",
    })
    assert r.status_code == 422


async def test_create_route_valid_purpose_succeeds(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p9", base_url="https://p9.example")
    r = await client.post(_ROUTES, json={
        "purpose": "popular_questions", "provider_id": str(provider.id), "model": "gpt-x",
    })
    assert r.status_code == 201
    assert r.json()["purpose"] == "popular_questions"


async def test_test_route_success(client, db_session, as_principal):
    as_principal()
    from app.services.llm import client as llm_client
    llm_client.invalidate()
    provider = await llm_repo.create_provider(db_session, name="pt", base_url="https://pt.example", api_key="k")
    await llm_repo.create_route(db_session, purpose="classification", provider_id=provider.id, model="m1")
    body = {"model": "m1", "choices": [{"message": {"content": "pong"}}]}
    factory, _ = _mock_httpx(body)
    with patch.object(llm_client.httpx, "AsyncClient", factory):
        r = await client.post(f"{_ROUTES}/classification/test")
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is True
    assert out["model"] == "m1"
    assert out["latency_ms"] >= 0


async def test_test_route_disabled_returns_ok_false(client, db_session, as_principal):
    as_principal()
    from app.services.llm import client as llm_client
    llm_client.invalidate()
    provider = await llm_repo.create_provider(db_session, name="pt2", base_url="https://pt2.example", api_key="k")
    await llm_repo.create_route(db_session, purpose="brief", provider_id=provider.id, model="m", enabled=False)
    r = await client.post(f"{_ROUTES}/brief/test")
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is False
    assert "no enabled route" in out["error"]


async def test_test_route_unknown_purpose_404(client, as_principal):
    as_principal()
    r = await client.post(f"{_ROUTES}/nope/test")
    assert r.status_code == 404


async def test_test_route_requires_admin(client, as_principal):
    as_principal(role="user", scopes=_USER_SCOPES)
    r = await client.post(f"{_ROUTES}/classification/test")
    assert r.status_code == 403


async def test_mutation_invalidates_route_cache(client, monkeypatch, as_principal):
    as_principal()
    mock_invalidate = MagicMock()
    monkeypatch.setattr("app.routers.llm.invalidate", mock_invalidate)
    r = await client.post(_PROVIDERS, json={"name": "p7", "base_url": "https://p7.example"})
    assert r.status_code == 201
    mock_invalidate.assert_called_once()
