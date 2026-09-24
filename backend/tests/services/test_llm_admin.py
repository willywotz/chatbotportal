"""Unit tests for the LLM provider/binding admin CRUD service."""
import uuid

import pytest

from app.core.errors import ApiError
from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services import admin as llm_admin

pytestmark = pytest.mark.asyncio


async def test_create_provider_persists(db_session):
    provider = await llm_admin.create_provider(
        db_session, {"name": "p1", "provider": "openai", "model": "m"})
    assert await llm_repo.get_provider(db_session, provider.id) is not None


async def test_create_provider_unknown_kind_raises_422(db_session):
    with pytest.raises(ApiError) as exc:
        await llm_admin.create_provider(
            db_session, {"name": "px", "provider": "not-a-kind", "model": "m"})
    assert exc.value.status == 422


async def test_list_providers_returns_all(db_session):
    await llm_repo.create_provider(db_session, name="p1", provider="openai", model="m")
    await llm_repo.create_provider(db_session, name="p2", provider="openai", model="m")
    assert len(await llm_admin.list_providers(db_session)) == 2


async def test_get_provider_not_found_raises_404(db_session):
    with pytest.raises(ApiError) as exc:
        await llm_admin.get_provider(db_session, uuid.uuid4())
    assert exc.value.status == 404


async def test_update_provider_applies_fields(db_session):
    provider = await llm_repo.create_provider(
        db_session, name="p1", provider="openai", model="m", api_key="k")
    updated = await llm_admin.update_provider(db_session, provider.id, {"timeout_seconds": 30.0})
    assert updated.timeout_seconds == 30.0
    assert updated.api_key == "k"


async def test_delete_provider_in_use_raises_409(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", provider="openai", model="m")
    await llm_repo.create_binding(db_session, purpose="judge", provider_id=provider.id)
    with pytest.raises(ApiError) as exc:
        await llm_admin.delete_provider(db_session, provider.id)
    assert exc.value.status == 409
    assert await llm_repo.get_provider(db_session, provider.id) is not None


async def test_create_binding_unknown_provider_raises_404(db_session):
    with pytest.raises(ApiError) as exc:
        await llm_admin.create_binding(
            db_session, {"purpose": "brief", "provider_id": uuid.uuid4()})
    assert exc.value.status == 404


async def test_create_binding_duplicate_purpose_raises_409(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", provider="openai", model="m")
    await llm_repo.create_binding(db_session, purpose="brief", provider_id=provider.id)
    with pytest.raises(ApiError) as exc:
        await llm_admin.create_binding(
            db_session, {"purpose": "brief", "provider_id": provider.id})
    assert exc.value.status == 409


async def test_update_binding_new_provider_not_found_raises_404(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", provider="openai", model="m")
    binding = await llm_repo.create_binding(db_session, purpose="brief", provider_id=provider.id)
    with pytest.raises(ApiError) as exc:
        await llm_admin.update_binding(db_session, binding.id, {"provider_id": uuid.uuid4()})
    assert exc.value.status == 404


async def test_delete_binding_removes_it(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", provider="openai", model="m")
    binding = await llm_repo.create_binding(db_session, purpose="brief", provider_id=provider.id)
    await llm_admin.delete_binding(db_session, binding.id)
    await db_session.flush()
    assert await llm_repo.get_binding(db_session, binding.id) is None
