"""Unit tests for the LLM provider/route admin CRUD service.

Router-level behavior (status codes, masking, cache invalidation) stays
covered by tests/routers/test_llm_admin.py; these tests exercise the ORM
access moved out of the router.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models import LlmProvider, LlmRoute
from app.services.llm import admin as llm_admin


@pytest.mark.asyncio
async def test_create_provider_persists(db):
    provider = await llm_admin.create_provider({"name": "p1", "base_url": "https://p1.example"})
    assert await LlmProvider.filter(id=provider.id).exists()


@pytest.mark.asyncio
async def test_list_providers_returns_all(db):
    await LlmProvider.create(name="p1", base_url="https://p1.example")
    await LlmProvider.create(name="p2", base_url="https://p2.example")
    assert len(await llm_admin.list_providers()) == 2


@pytest.mark.asyncio
async def test_get_provider_not_found_raises_404(db):
    with pytest.raises(HTTPException) as exc:
        await llm_admin.get_provider(uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_provider_applies_fields(db):
    provider = await LlmProvider.create(name="p1", base_url="https://p1.example", api_key="k")
    updated = await llm_admin.update_provider(provider.id, {"timeout_seconds": 30.0})
    assert updated.timeout_seconds == 30.0
    assert updated.api_key == "k"  # untouched field stays


@pytest.mark.asyncio
async def test_delete_provider_removes_it(db):
    provider = await LlmProvider.create(name="p1", base_url="https://p1.example")
    await llm_admin.delete_provider(provider.id)
    assert not await LlmProvider.filter(id=provider.id).exists()


@pytest.mark.asyncio
async def test_delete_provider_in_use_raises_409(db):
    provider = await LlmProvider.create(name="p1", base_url="https://p1.example")
    await LlmRoute.create(purpose="judge", provider=provider, model="m")
    with pytest.raises(HTTPException) as exc:
        await llm_admin.delete_provider(provider.id)
    assert exc.value.status_code == 409
    assert await LlmProvider.filter(id=provider.id).exists()


@pytest.mark.asyncio
async def test_create_route_unknown_provider_raises_404(db):
    with pytest.raises(HTTPException) as exc:
        await llm_admin.create_route({"purpose": "brief", "provider_id": uuid.uuid4(), "model": "m"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_route_duplicate_purpose_raises_409(db):
    provider = await LlmProvider.create(name="p1", base_url="https://p1.example")
    await LlmRoute.create(purpose="brief", provider=provider, model="m")
    with pytest.raises(HTTPException) as exc:
        await llm_admin.create_route({"purpose": "brief", "provider_id": provider.id, "model": "m2"})
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_route_new_provider_not_found_raises_404(db):
    provider = await LlmProvider.create(name="p1", base_url="https://p1.example")
    route = await LlmRoute.create(purpose="brief", provider=provider, model="m")
    with pytest.raises(HTTPException) as exc:
        await llm_admin.update_route(route.id, {"provider_id": uuid.uuid4()})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_route_duplicate_purpose_raises_409(db):
    provider = await LlmProvider.create(name="p1", base_url="https://p1.example")
    await LlmRoute.create(purpose="brief", provider=provider, model="m")
    other = await LlmRoute.create(purpose="judge", provider=provider, model="m")
    with pytest.raises(HTTPException) as exc:
        await llm_admin.update_route(other.id, {"purpose": "brief"})
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_route_removes_it(db):
    provider = await LlmProvider.create(name="p1", base_url="https://p1.example")
    route = await LlmRoute.create(purpose="brief", provider=provider, model="m")
    await llm_admin.delete_route(route.id)
    assert not await LlmRoute.filter(id=route.id).exists()


@pytest.mark.asyncio
async def test_route_provider_name_resolves_fk(db):
    provider = await LlmProvider.create(name="p1", base_url="https://p1.example")
    route = await LlmRoute.create(purpose="brief", provider=provider, model="m")
    assert await llm_admin.route_provider_name(route) == "p1"
