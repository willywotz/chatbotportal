"""Admin CRUD API for LLM providers, bindings, kinds, and purposes."""
import uuid

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services import providers, rate_limit
from app.features.llm.services.providers import ProviderSpec
from app.features.settings.routers.settings import MASK
from app.features.llm.services import KNOWN_PURPOSES

_PROVIDERS = "/api/v1/language-model/providers"
_BINDINGS = "/api/v1/language-model/bindings"
_PURPOSES = "/api/v1/language-model/purposes"
_KINDS = "/api/v1/language-model/kinds"

_USER_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


@pytest.fixture
def fake_kind():
    if "fakeradmin" not in providers.known_kinds():
        providers.register(ProviderSpec(
            kind="fakeradmin", model_provider="openai", transient_errors=(),
            map_error=lambda e: None,
            build_model=lambda model, **kw: GenericFakeChatModel(
                messages=iter([AIMessage(content="pong")]))))
    rate_limit.reset_cache()
    yield


async def test_create_provider_returns_masked_key(client, db_session, as_principal):
    as_principal()
    r = await client.post(_PROVIDERS, json={
        "name": "openai-p", "provider": "openai", "model": "gpt-4o", "api_key": "sk-real-secret",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["api_key"] == MASK
    stored = await llm_repo.get_provider(db_session, uuid.UUID(body["id"]))
    assert stored.api_key == "sk-real-secret"


async def test_create_provider_unknown_kind_422(client, as_principal):
    as_principal()
    r = await client.post(_PROVIDERS, json={"name": "bad", "provider": "nope", "model": "m"})
    assert r.status_code == 422


async def test_list_providers_masks_api_key(client, db_session, as_principal):
    as_principal()
    await llm_repo.create_provider(db_session, name="p1", provider="openai", model="m", api_key="super-secret")
    r = await client.get(_PROVIDERS)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["data"][0]["api_key"] == MASK


async def test_update_with_mask_keeps_stored_key(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p2", provider="openai", model="m", api_key="original-key")
    r = await client.patch(f"{_PROVIDERS}/{provider.id}", json={"api_key": MASK, "timeout_seconds": 30.0})
    assert r.status_code == 200
    assert r.json()["api_key"] == MASK
    stored = await llm_repo.get_provider(db_session, provider.id)
    assert stored.api_key == "original-key"
    assert stored.timeout_seconds == 30.0


async def test_update_with_null_api_key_keeps_stored_key(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p2b", provider="openai", model="m", api_key="original-key-2")
    r = await client.patch(f"{_PROVIDERS}/{provider.id}", json={"api_key": None})
    assert r.status_code == 200
    stored = await llm_repo.get_provider(db_session, provider.id)
    assert stored.api_key == "original-key-2"


async def test_create_binding_ok(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p3", provider="openai", model="gpt-x")
    r = await client.post(_BINDINGS, json={
        "purpose": "classification", "provider_id": str(provider.id),
    })
    assert r.status_code == 201
    body = r.json()
    assert body["provider_name"] == "p3"
    assert body["purpose"] == "classification"
    assert body["model"] == "gpt-x"
    assert body["model_override"] is None


async def test_binding_response_includes_model_override(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p3b", provider="openai", model="gpt-x")
    binding = await llm_repo.create_binding(
        db_session, purpose="brief", provider_id=provider.id, model_override="gpt-4o-mini")
    r = await client.get(f"{_BINDINGS}/{binding.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["model_override"] == "gpt-4o-mini"
    assert body["model"] == "gpt-4o-mini"


async def test_create_binding_unknown_provider_404(client, as_principal):
    as_principal()
    r = await client.post(_BINDINGS, json={
        "purpose": "classification", "provider_id": str(uuid.uuid4()),
    })
    assert r.status_code == 404


async def test_create_binding_duplicate_purpose_409(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p4", provider="openai", model="gpt-x")
    await llm_repo.create_binding(db_session, purpose="brief", provider_id=provider.id)
    r = await client.post(_BINDINGS, json={"purpose": "brief", "provider_id": str(provider.id)})
    assert r.status_code == 409


async def test_create_binding_invalid_purpose_422(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p8", provider="openai", model="m")
    r = await client.post(_BINDINGS, json={"purpose": "nope", "provider_id": str(provider.id)})
    assert r.status_code == 422


async def test_delete_provider_in_use_409(client, db_session, as_principal):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="p5", provider="openai", model="m")
    await llm_repo.create_binding(db_session, purpose="judge", provider_id=provider.id)
    r = await client.delete(f"{_PROVIDERS}/{provider.id}")
    assert r.status_code == 409
    assert await llm_repo.get_provider(db_session, provider.id) is not None


async def test_non_admin_create_provider_403(client, as_principal):
    as_principal(role="user", scopes=_USER_SCOPES)
    r = await client.post(_PROVIDERS, json={"name": "p6", "provider": "openai", "model": "m"})
    assert r.status_code == 403


async def test_list_purposes_returns_known_purposes(client, as_principal):
    as_principal()
    r = await client.get(_PURPOSES)
    assert r.status_code == 200
    assert r.json() == {"data": list(KNOWN_PURPOSES)}


async def test_list_kinds_returns_openai(client, as_principal):
    as_principal()
    r = await client.get(_KINDS)
    assert r.status_code == 200
    assert "openai" in r.json()["data"]


async def test_binding_test_success(client, db_session, as_principal, fake_kind):
    as_principal()
    provider = await llm_repo.create_provider(db_session, name="pt", provider="fakeradmin", model="m1")
    await llm_repo.create_binding(db_session, purpose="brief", provider_id=provider.id)
    r = await client.post(f"{_BINDINGS}/brief/test")
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_binding_test_no_binding_returns_ok_false(client, as_principal):
    as_principal()
    r = await client.post(f"{_BINDINGS}/brief/test")
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is False
    assert "no enabled binding" in out["error"]


async def test_binding_test_unknown_purpose_404(client, as_principal):
    as_principal()
    r = await client.post(f"{_BINDINGS}/nope/test")
    assert r.status_code == 404


async def test_binding_test_requires_admin(client, as_principal):
    as_principal(role="user", scopes=_USER_SCOPES)
    r = await client.post(f"{_BINDINGS}/classification/test")
    assert r.status_code == 403


async def test_mutation_invalidates_cache(client, monkeypatch, as_principal):
    as_principal()
    from unittest.mock import MagicMock
    mock_invalidate = MagicMock()
    monkeypatch.setattr("app.features.llm.routers.llm.invalidate", mock_invalidate)
    r = await client.post(_PROVIDERS, json={"name": "p7", "provider": "openai", "model": "m"})
    assert r.status_code == 201
    mock_invalidate.assert_called_once()
